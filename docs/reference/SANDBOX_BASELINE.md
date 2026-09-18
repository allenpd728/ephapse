# Sandbox baseline — measured 2026-09-18

Raw evidence for the constraints stated in `docs/AGENT_HANDOFF.md`. Every
number here came from a command run in an actual OpenHands Cloud sandbox,
not from documentation. Re-measure before sizing an experiment; provisioning
can change.

> **Revised 2026-09-18 (issue #1, run `20260918-1455-ezlh`).** This session
> added the three gaps the scaffolding session left open (disk quota,
> egress stability, hooked-run RSS) and corrected a latency figure that
> would have mis-sized every later experiment. See §Latency.

## Host resources

Command: `free -h; df -h; nproc; nvidia-smi -L`

```
              total   used   free  shared  buff/cache  available
Mem:           15Gi   2.5Gi  1.1Gi   42Mi        12Gi       13Gi
Swap:            0B

4 CPU cores
nvidia-smi: command not found        # no GPU
Python 3.13.15
```

**The handoff doc's original "24GB RAM" figure was wrong.** Measured total
is 15 GiB, with ~13 GiB available once the base image is running. Size
experiments against 13 GiB.

### Gap closed: is the cap enforced, or just reported?

`/sys/fs/cgroup/memory.max` returns **`max`** and `/sys/fs/cgroup/cpu.max`
returns **`max 100000`** — both unconstrained. So the 15 GiB is the *host's
physical RAM*, not a container-enforced cap. There is no cgroup ceiling to
hit and no OOM-kill guarantee at a known number: if a run exceeds physical
RAM it will degrade or fail unpredictably rather than at a clean limit.

Practical consequence: treat **~10 GB as the working budget** for any single
run (model + cache + Python), leaving headroom on a machine shared with the
agent. Do not size to 13 GB. `/sys/fs/cgroup/memory.peak` is readable for
post-hoc peak checks.

## Disk

| Mount | Size | Free | Notes |
|---|---|---|---|
| `/` (overlay) | 72 GB | **58 GB** | container layer; where HF cache and pip land |
| `/workspace` | 25 GB | 25 GB | separate `ext4` on `/dev/nvme0n2` |

Measured checkpoints: Pythia-70M ≈ **159 MB** on disk in a fresh
`HF_HOME`; Pythia-160M ≈ 1.1 GB with tokenizer and configs. At 58 GB free,
disk is not a binding constraint for any planned model size.

**No enforced quota was found** to compare against observed free space — the
figure above is the overlay's real free space, which is what matters. If a
quota is imposed in future, `df` on `/` will show it.

## Network egress

Bare-host `curl` to CDN roots returns `000`/`403` (no index at `/`), which is
not a reachability signal. Reachability was therefore tested on **real
requests**:

| Target | Result |
|---|---|
| `huggingface.co` (API + metadata) | 200 |
| `hf_hub_download` of `config.json` | 0.2 s |
| `hf_hub_download` of `model.safetensors` (166 MB) | **6.8 s → 24.6 MB/s** |
| `neuronpedia.org` | 200 |
| `pypi.org` | 200 |
| `api.github.com` | 200 |

**Conclusion: egress is not allowlist-restricted and the full HuggingFace
download path works, including LFS/CDN**, at ~25 MB/s. A 1 GB checkpoint is
under a minute. Repeated requests were stable (three consecutive calls, no
failures).

One observation worth carrying: unauthenticated HF requests emit a
rate-limit warning. A sweep issuing *many* metadata calls should set
`HF_TOKEN` to avoid throttling.

## Toolchain

```
torch                2.14.0+cpu
transformer-lens     3.9.0
sae-lens             6.51.0
```

All three install cleanly from PyPI plus the PyTorch CPU index. Note: the
environment **is not persistent across sessions** — torch was absent at the
start of this run and had to be reinstalled. Any experiment must assume a
cold environment or pin via `requirements.txt`.

`HookedTransformer.from_pretrained` is deprecated in TransformerLens 3.9.0
in favour of `TransformerBridge.boot_transformers(...)` +
`enable_compatibility_mode()`. The old path still works but warns; the
deprecation is not yet a breakage.

## Model load and memory

| Model | Load (warm cache) | Peak RSS (bare forward) |
|---|---|---|
| pythia-70m | — | 1.52 GB |
| pythia-160m | 9.1 s | 2.68 GB |

Config of the 160M target: `n_layers=12, d_model=768, d_vocab=50304`,
162.3M params.

### Gap closed: peak RSS for a *real* probe (hooks caching activations)

Measured with `run_with_cache` on `blocks.{3,6,9}.hook_resid_post`, 64 prompts
of 32 tokens, fp32
(`experiments/2026-09-18-sandbox-baseline-hooked.py`):

```
interpreter start      : 0.48 GB
model loaded           : 2.68 GB
after hooked run       : 2.68 GB   <- no measurable increase
cache on device        : 6.6 MB for 64 prompts x 3 layers
```

**The cache is negligible at this scale: 0.11 MB per prompt for 3 layers.**
Projected:

| Prompts | Cache (3 layers) |
|---|---|
| 500 | 55 MB |
| 2,000 | 221 MB |
| 10,000 | 1.1 GB |

So `run_with_cache` is *not* the memory risk. The risk is holding many
cached tensors **in a Python list** rather than aggregating per prompt —
which is what a naive sweep does. Aggregate, don't accumulate.

Note the earlier "2.65 GB" and today's "2.68 GB" agree within noise; the
fp32 default is the reason 162M params cost ~2.7 GB rather than ~0.65 GB.

## Latency — corrected, and this mattered

The scaffolding session recorded "~217 ms per forward pass" from 5 sequential
single-prompt calls. Measured today at **207 ms/call** — consistent. But that
is **per-call overhead at batch size 1**, not throughput, and using it to
size a sweep overstates cost by roughly **10x**
(`experiments/2026-09-18-latency-vs-batch.py`):

| Workload | Per-prompt |
|---|---|
| 1 prompt, sequential calls | 207 ms |
| batch of 1 | 204 ms |
| batch of 8 | 42 ms |
| batch of 32 | 25 ms |
| batch of 64 | 21 ms |

**Size sweeps on the batched figure.** A 2,000-prompt sweep at 160M is
~40 s of forward-pass time at batch 64, not the ~7 minutes the earlier
figure implied. This makes the paraphrase probe and the detector
positive-control cheaper than the handoff doc assumed, and it removes the
"larger models are impractical" worry for *batched eval* (it still applies to
interactive single-prompt iteration).

The 217 ms figure stays correct for interactive work — steering one prompt at
a time is genuinely that slow.

## Neuronpedia API

Confirmed working:

```
GET /api/feature/{modelId}/{saeId}/{index}   ->  HTTP 200, JSON
```

Returns real feature data including `modelId`, `layer`, `index`,
`maxActApprox`, `frac_nonzero`, `vector` (decoder direction),
`neuron_alignment_*`, `topkCosSim*`.

Example: `GET /api/feature/gpt2-small/9-res-jb/21474` →
`frac_nonzero=0.0013`, `maxActApprox=41.96`, `hookName` present.

Unconfirmed:

```
POST /api/search-all    ->  HTTP 500 on the payload tried; endpoint exists
                           (405 on GET, not 404) but the request schema is
                           not yet pinned down.
```

Do not design an experiment around `/api/search-all` until its payload is
confirmed. The feature endpoint is safe to build on now.

**The feature's `vector` field is the useful one for validation**: it is the
decoder direction, so it can be used to test a candidate feature against
held-out text. Note that Neuronpedia's feature *explanations* are autointerp
output — treat them as another model's guess, not ground truth.
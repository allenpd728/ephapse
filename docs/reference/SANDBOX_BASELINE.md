# Sandbox baseline — measured 2026-09-18

Raw evidence for the constraints stated in `docs/AGENT_HANDOFF.md`. Every
number here came from a command run in an actual OpenHands Cloud sandbox,
not from documentation. Re-measure before sizing an experiment; provisioning
can change.

> **Revised 2026-09-18 (issue #1, run `20260918-1455-ezlh`).** This session
> added the three gaps the scaffolding session left open (disk quota,
> egress stability, hooked-run RSS) and corrected a latency figure that
> would have mis-sized every later experiment. See §Latency.
>
> **Revised again 2026-09-18 (issue #2, run `20260918-1720-altu`).** Added
> the §Model and SAE availability section, which constrains the model choice
> for every later issue, and corrected the §Neuronpedia API claim about
> decoder vectors. See that section.

## Model and SAE availability — this constrains the model choice

**Measured 2026-09-18 (issue #2).** The handoff doc recommends "Pythia-70M to
~410M". That range is **wrong for the cross-check requirement**, and the correct
set is narrower.

Queried via `sae_lens.loading.pretrained_saes_directory.get_pretrained_saes_directory()`:

| Release | Model | Hooks covered |
|---|---|---|
| `pythia-70m-deduped-res-sm` | pythia-**70m-deduped** | 7 (resid_pre + resid_post L0–L5) |
| `pythia-70m-deduped-att-sm` | pythia-70m-deduped | 6 (attn_out) |
| `pythia-70m-deduped-mlp-sm` | pythia-70m-deduped | 6 (mlp_out) |
| 4 × `sae_bench_pythia70m_sweep_*` | pythia-70m-deduped | 40–56 (SAEBench sweeps) |

**Total pythia releases in SAELens: 7. All are pythia-70m-deduped. There is no
pythia-160m SAE release, and no non-deduped pythia-70m release.**

Consequences, which every later issue must respect:

1. **Use `pythia-70m-deduped`, not `pythia-160m`.** Every "Pythia-160M" reference
   in the handoff doc and in the #1 baseline is computationally fine but cannot
   be paired with an SAE. If a 160M target is wanted later, an SAE must be
   trained — out of scope for this stage.
2. **`d_model=512`, `n_layers=6`** (smaller than 160M's 768/12). Latency and
   memory are therefore *better* than the #1 figures; the #1 numbers remain
   valid as upper bounds.
3. **`neuronpedia_id` is the bridge.** The SAELens directory carries a
   per-hook `neuronpedia_id` mapping, e.g.
   `blocks.3.hook_resid_post -> 'pythia-70m-deduped/3-res-sm'`. That is how a
   local SAE is matched to its hosted copy — do not guess the naming.

## End-to-end toolchain verification (issue #2)

`experiments/2026-09-18-toolchain-neuronpedia-crosscheck.py`, run
`20260918-1720-altu`:

```
d_model=512  n_layers=6
SAE loaded: d_in=512  d_sae=32768
local top-5 active features: [(20526, 51.49), (7254, 23.43), (32409, 17.01),
                             (1812, 16.50), (5355, 16.40)]

   idx  local max  NP maxActApprox    ratio  hookName match
 20526     51.491           56.738    0.908            True
  7254     23.431           26.307    0.891            True
 32409     17.007            3.604    4.719            True
  1812     16.505           43.701    0.378            True
  5355     16.401           59.604    0.275            True

local W_dec shape: (32768, 512)  (d_sae, d_model)
```

**Interpretation, stated carefully.** The two sources are the *same feature set*
(a `d_in` of 512 matches `d_model`, `d_sae=32768` is the documented width, and
`hookName` agrees on every queried feature). Magnitudes are the same order for
4 of 5 features.

**But ratios span 0.275x to 4.7x, and that is expected, not a failure.**
`maxActApprox` is Neuronpedia's maximum over *their* activation dataset; the
local figure is the max over *8 prompts*. Neither bounds the other, so a local
max exceeding the hosted approximation (feature 32409, 4.7x) is possible.
**This is a sanity check on identity, not a calibration of values** — treat
agreement in magnitude as sufficient, and do not use `maxActApprox` as a
reference value for anything quantitative.

## Neuronpedia API — corrected

Earlier in this document (and in DEC-003) it was claimed that the feature
endpoint's `vector` field "is the decoder direction, so it can be used to test
a candidate feature against held-out text." **That is wrong in practice.**

Measured across five `pythia-70m-deduped/3-res-sm` features and one
`gpt2-small/9-res-jb` feature:

```
hasVector: False   vector: [] (length 0)   vectorLabel: None
...also with ?includeVector=true -> still length 0
```

**The decoder direction is not retrievable from the API.** The good news is
that it is unnecessary: the decoder direction is available **locally** from
SAELens as `sae.W_dec`, shape `(d_sae, d_model)` — confirmed `(32768, 512)` for
the pythia SAE. Local is strictly better for this purpose: it needs no rate
limit, no network, and no trust in a hosted copy.

**Consequence:** the remote-probing path (DEC-003) is for *inspecting* hosted
features — dashboards, top activations, `maxActApprox`, autointerp labels — not
for obtaining vectors. Any experiment needing a decoder direction uses the
local `W_dec`.

## Host resources (unchanged)

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
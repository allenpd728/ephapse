# Sandbox baseline — measured 2026-09-18

Raw evidence for the constraints stated in `docs/AGENT_HANDOFF.md`. Every
number here came from a command run in an actual OpenHands Cloud sandbox,
not from documentation. Re-measure before sizing an experiment; provisioning
can change.

## Host resources

Command: `free -h; df -h; nproc; nvidia-smi -L`

```
              total   used   free  shared  buff/cache  available
Mem:           15Gi   2.5Gi  1.1Gi   42Mi        12Gi       13Gi
Swap:            0B

overlay  72G  18G  55G  25% /      # 55 GB free
4 CPU cores
nvidia-smi: command not found        # no GPU
Python 3.13.15
```

**The handoff doc's original "24GB RAM" figure was wrong.** Measured total
is 15 GiB, with ~13 GiB available once the base image is running. Size
experiments against 13 GiB.

## Network egress

Command: `curl -s -o /dev/null -w "%{http_code}" <host>`

| Host | HTTP |
|---|---|
| https://huggingface.co | 200 |
| https://www.neuronpedia.org | 200 |
| https://pypi.org | 200 |

Egress was not allowlist-restricted at measurement time. This is worth
re-checking per session rather than assuming.

## Toolchain

```
torch                2.14.0+cpu
transformer-lens     3.9.0
sae-lens             6.51.0
```

Both interpretability libraries installed and imported cleanly. Note:
`HookedTransformer.from_pretrained` is deprecated in TransformerLens 3.9.0
in favour of `TransformerBridge.boot_transformers(...)` +
`enable_compatibility_mode()`. The old path still works but emits a
DeprecationWarning.

## Model load and latency (CPU, no GPU)

| Model | Load time | Peak RSS | Forward pass (warm) |
|---|---|---|---|
| pythia-70m | 10.9 s (cold download) | 1.52 GB | 121 ms/call |
| pythia-160m | 7.6 s (warm cache) | 2.65 GB | 217 ms/call |

Forward-pass figures are the mean of 5 consecutive calls on a single core
of the 4 available, prompt "The Eiffel Tower is located in the city of",
under `torch.no_grad()`. Measured with `resource.getrusage(...).ru_maxrss`.

Config of the 160M target: `n_layers=12, d_model=768, d_vocab=50304`,
162.3M params.

**Implication for experiment sizing.** A 2,000-prompt sweep at 160M is
~7 minutes of forward-pass time on one core before SAE encode overhead.
That is feasible. A 12B model at this latency would be impractical, which
is where the "70M–410M for iterative work" guidance comes from.

**Note the fp32 default.** 162M params × 4 bytes = ~0.65 GB of weights, but
peak RSS was 2.65 GB — TransformerLens overhead and activations dominate.
fp16 dtype would roughly halve the weight term. Parameter count alone is
not the constraint; dtype and cached activations are.

## Neuronpedia API

Confirmed working:

```
GET /api/feature/{modelId}/{saeId}/{index}   →  HTTP 200, JSON
```

Returns real feature data including `modelId`, `layer`, `index`,
`maxActApprox`, `frac_nonzero`, `vector` (decoder direction),
`neuron_alignment_*`, `topkCosSim*`.

Example: `GET /api/feature/gpt2-small/9-res-jb/21474` →
`frac_nonzero=0.0013`, `maxActApprox=41.96`, `hookName` present.

Unconfirmed:

```
POST /api/search-all    →  HTTP 500 on the payload tried; endpoint exists
                           (405 on GET, not 404) but the request schema is
                           not yet pinned down.
```

Do not design an experiment around `/api/search-all` until its payload is
confirmed. The feature endpoint is safe to build on now.

**The feature's `vector` field is the useful one for validation**: it is the
decoder direction, so it can be used to test a candidate feature against
held-out text. Note that Neuronpedia's feature *explanations* are autointerp
output — treat them as another model's guess, not ground truth.
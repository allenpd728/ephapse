#!/usr/bin/env python3
"""measure_footprint.py -- predict a model's memory footprint before loading it.

Why this exists
---------------
Issue #39 burned seven runs on the same failure. Each claimed the task, reported
that it had died in "the ~10 GB dependency-install phase", and went stale. The
install is not the problem: `pip install -r requirements.txt` completes in ~65 s
and installs 166 MB of wheels. The real failure is the model load plus the
batch forward that follows it.

Measured in this sandbox (15 GiB RAM, no swap):

    gemma-2-2b, fp32   peak RSS 11.48 GB   MemAvailable left 2.54 GB
    batch-64 forward   logits alone = 64 x seq x 256000 x 4 B ~= 2.1 GB more

The 2.54 GB of headroom cannot hold the activation and logits buffers, so the
process is OOM-killed. Because the kill takes the terminal with it, the run
leaves no trace -- which is exactly why the diagnosis stayed wrong for two days
and the claim kept cycling.

This tool does two things:

  `plan`  compute the footprint from the published config alone -- a 2 KB
          download, no weights, no torch. Cheap enough to run before claiming.
  `load`  measure the real peak RSS under an optional address-space cap, so an
          OOM raises MemoryError and is *reported* instead of killing the sandbox.

The `plan` numbers are arithmetic on the config; the `load` numbers are measured.
They are reported separately and never conflated. A `plan` that disagrees with a
`load` is a finding.

Usage
-----
    python3 tooling/measure_footprint.py plan --model google/gemma-2-2b
    python3 tooling/measure_footprint.py plan --model google/gemma-2-2b --dtype bf16
    python3 tooling/measure_footprint.py load --model unsloth/gemma-2-2b --cap-gb 14.0
    python3 tooling/measure_footprint.py load --model EleutherAI/pythia-70m-deduped --batch 64 --json

Exit codes: 0 = measured, 3 = the plan exceeds the budget (do not attempt the
load), 4 = the load OOM'd under the cap (a measurement, not an error).
"""

from __future__ import annotations

import argparse
import json
import re
import resource
import sys
import time
import urllib.error
import urllib.request

# Byte size of one parameter per dtype. `int8` is a quantised weight-only load;
# activations stay fp32, which is why its saving is smaller than the name implies.
DTYPE_BYTES = {"fp32": 4, "bf16": 2, "fp16": 2, "int8": 1}
# bf16/fp16 parameters, fp32 compute and activations.
ACTIVATION_BYTES = 4
# Interpreter + torch + transformers + allocator slack. Calibrated from a real
# load in this sandbox: gemma-2-2b fp32 weighed 10.46 GB of parameters and
# peaked at 11.48 GB RSS, so ~1.0 GB is non-parameter overhead. Without this
# term the plan under-predicts and calls a fatal config "TIGHT" rather than
# "EXCEEDS" -- which is exactly the mistake the #39 runs made by hand.
RUNTIME_OVERHEAD_GB = 1.0

GATED_401 = "the checkpoint is gated and this sandbox has no HF_TOKEN"
HF_CONFIG = "https://huggingface.co/{model}/resolve/main/config.json"
HF_API = "https://huggingface.co/api/models/{model}"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _check_id(model: str) -> str:
    if not _SAFE_ID.match(model) or ".." in model:
        raise ValueError(f"model id not accepted: {model!r}")
    return model


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ephapse-footprint"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def mem_available_gb() -> float:
    with open("/proc/meminfo") as f:
        fields = {ln.split(":")[0]: int(ln.split()[1]) for ln in f}
    return fields["MemAvailable"] / 1e6


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


# --------------------------------------------------------------------------- plan


def _normalise(cfg: dict, meta: dict) -> dict:
    return {
        "model_type": cfg.get("model_type"),
        "n_params": cfg.get("num_parameters"),
        "vocab_size": cfg.get("vocab_size", 256000),
        "hidden_size": cfg.get("hidden_size"),
        "n_layers": cfg.get("num_hidden_layers"),
        "n_heads": cfg.get("num_attention_heads"),
        "n_kv_heads": cfg.get("num_key_value_heads", cfg.get("num_attention_heads")),
        "intermediate": cfg.get("intermediate_size"),
        "tie_word_embeddings": cfg.get("tie_word_embeddings", False),
        "gated": meta.get("gated", False),
    }


def read_config(model: str, mirror: str | None = None) -> dict:
    """Fetch and normalise the model config (a couple of KB, no weights).

    `gated` is not a bool: HF reports `false`, `"auto"` or `"manual"`. Any value
    other than `False` means the config endpoint may 401, so the string is
    preserved in the result rather than coerced. `mirror` supplies the config
    from an architecture-identical public repo when the official one is gated.

    The parameter count comes from the API's `safetensors` block, which reports
    the true stored total and its dtype breakdown -- not from `config.json`,
    which carries no `num_parameters`. That makes the count exact rather than
    inferred from architecture.
    """
    model = _check_id(model)
    meta = _get_json(HF_API.format(model=model))
    gated = meta.get("gated", False)
    try:
        cfg = _get_json(HF_CONFIG.format(model=model))
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        if not mirror:
            raise PermissionError(
                f"{GATED_401} (gated={gated!r}); pass --mirror <public repo> to "
                "use an architecture-identical config") from e
        cfg = _get_json(HF_CONFIG.format(model=_check_id(mirror)))
        cfg["_config_from"] = mirror
    normalised = _normalise(cfg, meta)

    st = meta.get("safetensors") or {}
    if st.get("total"):
        normalised["n_params"] = st["total"]
        normalised["stored_dtypes"] = st.get("parameters", {})
    return normalised


def param_bytes(cfg: dict, n_params: int) -> int:
    """Exact parameter footprint, correcting for embedding storage.

    A config's `num_parameters` may count the input embedding twice (once as the
    embedding, once as the tied output head). Gemma ties them, so the true count
    is lower by `vocab x hidden`. Compute the correction rather than trusting
    either number.
    """
    v, h = cfg.get("vocab_size"), cfg.get("hidden_size")
    if cfg.get("tie_word_embeddings") and v and h and n_params > v * h:
        return (n_params - v * h) * 4  # param count is in fp32-equivalent units
    return n_params * 4


def plan(model: str, dtype: str, batch: int, seq: int,
         mirror: str | None = None) -> dict:
    cfg = read_config(model, mirror=mirror)
    n = cfg["n_params"]
    if not n:
        raise ValueError(f"config for {model} has no num_parameters")

    pbytes = param_bytes(cfg, n)
    # Real stored params differ from the fp32-equivalent count when the checkpoint
    # is bf16 or tied; take both so the discrepancy is visible, not hidden.
    n_eff = pbytes // 4
    wbytes = n_eff * DTYPE_BYTES[dtype]
    act = _activation_bytes(cfg, dtype, batch, seq)
    overhead = RUNTIME_OVERHEAD_GB * 1e9
    return {
        "model": model,
        "dtype": dtype,
        "config": cfg,
        "n_params_reported": n,
        "n_params_effective": n_eff,
        "weight_gb": wbytes / 1e9,
        "weights_only_gb": wbytes / 1e9,
        "runtime_overhead_gb": RUNTIME_OVERHEAD_GB,
        "weights_plus_batch_gb": (wbytes + act["total"] + overhead) / 1e9,
        "activation_breakdown_gb": {k: v / 1e9 for k, v in act.items()
                                    if k != "total"},
        "batch": batch,
        "seq": seq,
        "mem_available_gb": mem_available_gb(),
    }


def _activation_bytes(cfg: dict, dtype: str, batch: int, seq: int) -> dict:
    """Peak activation bytes for one forward pass at (batch, seq).

    The dominant term is the lm_head output: `batch x seq x vocab x 4 B`, before
    any softmax. FlashAttention keeps attention memory sub-quadratic, so it is
    modelled but not dominant.
    """
    if batch == 0:
        return {"logits": 0, "kv_cache": 0, "hidden": 0, "total": 0}
    h, L = cfg["hidden_size"], cfg["n_layers"]
    v = cfg["vocab_size"]
    n_kv = cfg["n_kv_heads"]
    head_dim = h // cfg["n_heads"]

    logits = batch * seq * v * ACTIVATION_BYTES
    kv_cache = 2 * L * batch * seq * n_kv * head_dim * ACTIVATION_BYTES
    hidden = batch * seq * h * ACTIVATION_BYTES
    return {"logits": logits, "kv_cache": kv_cache, "hidden": hidden,
            "total": logits + kv_cache + hidden}


def suggestions(cfg: dict, avail_gb: float, seq: int) -> list[str]:
    """Configurations that would fit the budget, cheapest change first.

    Answers "not feasible as specified -- feasible how?" without guessing.
    """
    out = []
    for dtype in ("bf16", "fp16", "int8"):
        p = _plan_from_cfg(cfg, dtype, 1, seq)
        if p["weights_plus_batch_gb"] <= avail_gb * 0.75:
            out.append(f"--dtype {dtype} at batch 1 "
                       f"({p['weights_plus_batch_gb']:.2f} GB)")
            break
    for batch in (1, 2, 4, 8):
        p = _plan_from_cfg(cfg, "bf16", batch, seq)
        if p["weights_plus_batch_gb"] <= avail_gb * 0.75:
            out.append(f"--batch {batch} with bf16 "
                       f"({p['weights_plus_batch_gb']:.2f} GB)")
            break
    return out


def _plan_from_cfg(cfg: dict, dtype: str, batch: int, seq: int) -> dict:
    n_eff = param_bytes(cfg, cfg["n_params"]) // 4
    act = _activation_bytes(cfg, dtype, batch, seq)
    total = n_eff * DTYPE_BYTES[dtype] + act["total"] + RUNTIME_OVERHEAD_GB * 1e9
    return {"weights_plus_batch_gb": total / 1e9}


def verdict(p: dict, budget_gb: float | None) -> tuple[str, str]:
    need = p["weights_plus_batch_gb"]
    avail = p["mem_available_gb"] if budget_gb is None else budget_gb
    label = "MemAvailable" if budget_gb is None else "--budget-gb"
    if need <= avail * 0.75:
        return "FITS", f"{need:.2f} GB vs {avail:.2f} GB {label} (<=75%)"
    if need <= avail:
        return "TIGHT", (f"{need:.2f} GB vs {avail:.2f} GB {label} -- under the "
                         "limit but no room for allocator fragmentation; cap the "
                         "process with RLIMIT_AS and chunk the batch")
    shortfall = need - avail
    return "EXCEEDS", (f"{need:.2f} GB vs {avail:.2f} GB {label} -- short by "
                       f"{shortfall:.2f} GB; record CPU infeasibility or reduce dtype/batch")


# --------------------------------------------------------------------------- load


def cmd_load(args) -> int:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cap = args.cap_gb
    if cap:
        # A soft cap turns an OOM into MemoryError, which we can report. Without
        # it the kernel kills the process and the sandbox loses the terminal.
        resource.setrlimit(resource.RLIMIT_AS, (int(cap * 1e9), int(cap * 1e9)))

    model_id = _check_id(args.model)
    torch_dtype = {"fp32": torch.float32, "bf16": torch.bfloat16,
                   "fp16": torch.float16, "int8": torch.float32}[args.dtype]
    out: dict = {"model": model_id, "dtype": args.dtype, "cap_gb": cap,
                 "torch": torch.__version__,
                 "mem_available_before_gb": mem_available_gb()}

    t0 = time.time()
    try:
        tok = AutoTokenizer.from_pretrained(model_id)
        kwargs = {"dtype": torch_dtype, "low_cpu_mem_usage": True}
        if args.dtype == "int8":
            # Weight-only quantisation; needs bitsandbytes, which is not pinned.
            print("  int8 load requires bitsandbytes; use --dtype bf16 instead",
                  file=sys.stderr)
            return 1
        model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        model.eval()
    except (MemoryError, RuntimeError, OSError, PermissionError) as e:
        out["stage"] = "load"
        out["result"] = "OOM_AT_LOAD" if _is_oom(e) else "LOAD_FAILED"
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        out["peak_rss_gb"] = peak_rss_gb()
        if "401" in str(e) or "gated" in str(e).lower():
            out["note"] = GATED_401
        _report(out, args)
        return 4 if out["result"] == "OOM_AT_LOAD" else 1

    out["load_s"] = time.time() - t0
    out["n_params"] = sum(p.numel() for p in model.parameters())
    out["peak_rss_after_load_gb"] = peak_rss_gb()
    out["mem_available_after_load_gb"] = mem_available_gb()

    if args.batch:
        prompts = ["The Eiffel Tower is located in the city of Paris"] * args.batch
        enc = tok(prompts, return_tensors="pt", padding=True)
        seq = int(enc["input_ids"].shape[1])
        out["batch"] = args.batch
        out["seq"] = seq
        t0 = time.time()
        try:
            with torch.no_grad():
                res = model(**enc)
            if args.logits:
                out["logits_shape"] = list(res.logits.shape)
                out["logits_gb"] = (
                    res.logits.numel() * res.logits.element_size() / 1e9)
            del res
            out["stage"] = "batch_forward"
            out["result"] = "OK"
            out["batch_s"] = time.time() - t0
        except (MemoryError, RuntimeError) as e:
            out["stage"] = "batch_forward"
            out["result"] = "OOM_AT_BATCH" if _is_oom(e) else "FORWARD_FAILED"
            out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    else:
        out["stage"] = "load"
        out["result"] = "OK"

    out["peak_rss_gb"] = peak_rss_gb()
    out["mem_available_after_gb"] = mem_available_gb()
    _report(out, args)
    return 0 if out["result"] == "OK" else 4


def _is_oom(e: BaseException) -> bool:
    s = str(e).lower()
    return isinstance(e, MemoryError) or "cannot allocate memory" in s or "out of memory" in s


def _report(out: dict, args) -> None:
    if getattr(args, "json", False):
        print(json.dumps(out, indent=2))
        return
    print(f"model {out['model']}  dtype {out['dtype']}"
          + (f"  cap {out['cap_gb']} GB" if out.get("cap_gb") else ""))
    print(f"  result               : {out['result']} (stage: {out.get('stage')})")
    if out.get("note"):
        print(f"  note                 : {out['note']}")
    if out.get("error"):
        print(f"  error                : {out['error']}")
    if out.get("load_s") is not None:
        print(f"  load wall            : {out['load_s']:.1f}s")
    if out.get("n_params"):
        print(f"  params               : {out['n_params']/1e9:.3f} B")
    if out.get("peak_rss_after_load_gb"):
        print(f"  peak RSS after load  : {out['peak_rss_after_load_gb']:.2f} GB")
    if out.get("peak_rss_gb"):
        print(f"  peak RSS total       : {out['peak_rss_gb']:.2f} GB")
    if out.get("mem_available_after_gb"):
        print(f"  MemAvailable after   : {out['mem_available_after_gb']:.2f} GB")


def cmd_plan(args) -> int:
    try:
        p = plan(args.model, args.dtype, args.batch, args.seq, mirror=args.mirror)
    except PermissionError as e:
        print(f"{args.model}: {e}", file=sys.stderr)
        return 1
    code, why = verdict(p, args.budget_gb)
    p["verdict"] = code
    p["verdict_reason"] = why
    if args.json:
        print(json.dumps(p, indent=2))
        return 0 if code == "FITS" else 3
    c = p["config"]
    print(f"{args.model}  [{args.dtype}]")
    print(f"  architecture      : {c['model_type']}  layers={c['n_layers']} "
          f"hidden={c['hidden_size']} heads={c['n_heads']} kv_heads={c['n_kv_heads']} "
          f"vocab={c['vocab_size']}")
    print(f"  params            : {p['n_params_effective']/1e9:.3f} B effective "
          f"(config reports {p['n_params_reported']/1e9:.3f} B)")
    print(f"  weights           : {p['weights_only_gb']:.2f} GB")
    if args.batch:
        b = p["activation_breakdown_gb"]
        print(f"  batch {args.batch} seq {args.seq} : logits {b['logits']:.2f} GB + "
              f"hidden {b['hidden']:.2f} GB + kv {b['kv_cache']:.2f} GB "
              f"= {sum(b.values()):.2f} GB")
    print(f"  runtime overhead  : {p['runtime_overhead_gb']:.2f} GB "
          "(interpreter + torch, calibrated)")
    print(f"  weights + batch   : {p['weights_plus_batch_gb']:.2f} GB")
    print(f"  verdict           : {code} -- {why}")
    if code != "FITS":
        avail = args.budget_gb if args.budget_gb is not None else p["mem_available_gb"]
        for s in suggestions(p["config"], avail, args.seq):
            print(f"  fits if           : {s}")
    return 0 if code == "FITS" else 3


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            v = f.read().strip()
        return None if v == "max" else int(v)
    except (OSError, ValueError):
        return None


def _mounts() -> list[tuple[str, str, str]]:
    out = []
    try:
        with open("/proc/mounts") as f:
            for ln in f:
                p = ln.split()
                if len(p) >= 3:
                    out.append((p[0], p[1], p[2]))
    except OSError:
        pass
    return out


def cmd_capacity(args) -> int:
    """Report every limit that can kill a load, not just MemTotal.

    Two traps this exists to surface, both of which mislead a naive
    `/proc/meminfo` read:

      * A cgroup memory limit can bind *below* MemTotal. The sandbox reports
        15 GiB total while the container is capped lower, so the crash looks
        inexplicable from inside the process.
      * `/workspace` and `/tmp` may be tmpfs, which is RAM-backed. A 5 GB
        checkpoint downloaded "to disk" then occupies RAM and counts against
        the same limit as the loaded model -- the download and the load each
        fit, but not together.
    """
    mem = {}
    with open("/proc/meminfo") as f:
        for ln in f:
            k, _, rest = ln.partition(":")
            mem[k] = int(rest.split()[0]) / 1e6
    cgroup_max = _read_int("/sys/fs/cgroup/memory.max")
    cgroup_cur = _read_int("/sys/fs/cgroup/memory.current")
    cgroup_peak = _read_int("/sys/fs/cgroup/memory.peak")
    swap_max = _read_int("/sys/fs/cgroup/memory.swap.max")

    tmpfs = [(src, mnt, fs) for src, mnt, fs in _mounts()
             if fs == "tmpfs" or "docker" in fs or "overlay" in fs]
    workspace_fs = "unknown"
    for src, mnt, fs in _mounts():
        if mnt == "/workspace":
            workspace_fs = f"{fs} ({src})"

    physical = mem.get("MemTotal", 0.0)
    binding = min([x for x in (physical, cgroup_max / 1e9 if cgroup_max else None)
                   if x] or [physical])

    out = {
        "physical_total_gb": physical,
        "mem_available_gb": mem.get("MemAvailable", 0.0),
        "swap_total_gb": mem.get("SwapTotal", 0.0),
        "cgroup_memory_max_gb": cgroup_max / 1e9 if cgroup_max else None,
        "cgroup_memory_current_gb": cgroup_cur / 1e9 if cgroup_cur else None,
        "cgroup_memory_peak_gb": cgroup_peak / 1e9 if cgroup_peak else None,
        "cgroup_swap_max_gb": swap_max / 1e9 if swap_max else None,
        "binding_limit_gb": binding,
        "workspace_filesystem": workspace_fs,
        "tmpfs_mounts": [f"{mnt} ({fs})" for _s, mnt, fs in tmpfs][:6],
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print("memory capacity")
    print(f"  MemTotal             : {out['physical_total_gb']:.2f} GB")
    print(f"  MemAvailable         : {out['mem_available_gb']:.2f} GB")
    print(f"  SwapTotal            : {out['swap_total_gb']:.2f} GB")
    cg = out["cgroup_memory_max_gb"]
    print(f"  cgroup memory.max    : {cg:.2f} GB" if cg else
          "  cgroup memory.max    : <unreadable or unlimited>")
    if out["cgroup_memory_peak_gb"]:
        print(f"  cgroup memory.peak   : {out['cgroup_memory_peak_gb']:.2f} GB")
    print(f"  binding limit        : {out['binding_limit_gb']:.2f} GB "
          "(plan/load compare against MemAvailable by default)")
    print(f"  /workspace fs        : {out['workspace_filesystem']}")
    if out["tmpfs_mounts"]:
        print(f"  tmpfs mounts         : {', '.join(out['tmpfs_mounts'])}")
        print("  NOTE: tmpfs is RAM-backed -- a checkpoint written to a tmpfs path")
        print("        is charged to the same limit as the loaded model.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Predict and measure model memory footprint before loading.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="compute the footprint from the config (no weights)")
    p.add_argument("--model", required=True)
    p.add_argument("--dtype", default="fp32", choices=sorted(DTYPE_BYTES))
    p.add_argument("--batch", type=int, default=0)
    p.add_argument("--seq", type=int, default=32)
    p.add_argument("--budget-gb", type=float, default=None,
                   help="override MemAvailable (default: read /proc/meminfo)")
    p.add_argument("--mirror", default=None,
                   help="public repo to read config.json from when --model is gated")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan)

    load = sub.add_parser("load", help="measure the real peak RSS under an optional cap")
    load.add_argument("--model", required=True)
    load.add_argument("--dtype", default="fp32", choices=sorted(DTYPE_BYTES))
    load.add_argument("--batch", type=int, default=0)
    load.add_argument("--logits", action="store_true", help="record logits shape/size")
    load.add_argument("--cap-gb", type=float, default=None,
                      help="RLIMIT_AS in GB; makes an OOM survivable")
    load.add_argument("--json", action="store_true")
    load.set_defaults(func=cmd_load)

    cap = sub.add_parser(
        "capacity", help="report every memory-relevant limit, including cgroup and tmpfs")
    cap.add_argument("--json", action="store_true")
    cap.set_defaults(func=cmd_capacity)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

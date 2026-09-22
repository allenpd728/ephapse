"""FAILING fixture for G-C4 — the isolate score computed over no-effect cases.

Drawn from DEC-020 (issue #7): the first version of the harness reported
`isolate = 0.996` across all 50 features, which reads like a strong result and
was computed entirely from cases where nothing happened (cause ~ 0). A reading
that cannot come out low is not a reading.

The only defect is that the `isolate` reading is not gated by the effect and
carries no guard, so it is computed over no-effect cases.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 0.05, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": true,
#                "records_both_groups": true},
#   "readings": [{"name": "cause", "depends_on_effect": true},
#                {"name": "isolate"}],
#   "comparability": {"model": "pythia-70m-deduped",
#                      "hook": "blocks.3.hook_resid_post",
#                      "threshold": 0.8, "n": 1500, "correction": "BH q=0.10"}
# }
# END-GATE-DECL

import numpy as np


def isolate_score(source_out, ablated_out) -> float:
    # trivially ~1.0 when nothing moved, i.e. when cause ~ 0
    return 1.0 - float(np.abs(source_out - ablated_out).mean())

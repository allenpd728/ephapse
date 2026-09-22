"""Clean fixture: a detector reading with a sound declared structure.

Issue #5 injected-correlation positive control, condensed to its declaration.
The point of the clean side is that every gate is SILENT here.

Model: pythia-70m-deduped, hook blocks.3.hook_resid_post, N=1500.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 0.05, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": true,
#                "records_both_groups": true},
#   "tests": [{"call": "poisson.sf", "known_answer": "k=3,lambda=1 -> 0.019"}],
#   "readings": [{"name": "detector_recovery", "depends_on_effect": true},
#                {"name": "isolate", "gated_by": "cause>0.01"}],
#   "comparability": {"model": "pythia-70m-deduped",
#                      "hook": "blocks.3.hook_resid_post",
#                      "threshold": 0.8, "n": 1500, "correction": "BH q=0.10"}
# }
# END-GATE-DECL

import numpy as np
from scipy import stats


def upper_tail(k: int, lam: float) -> float:
    # known-answer bound: poisson.sf(k-1, lam) is the correct upper tail
    return stats.poisson.sf(k - 1, lam)

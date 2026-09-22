"""FAILING fixture for G-C2 — a control that never fires.

Drawn from DEC-019 failure 3 (run 3): restricting to a low-support band but
still ranking by activation selected features the signal text never fires; the
planted row activated 0/20 of each group. The check that would have caught this
immediately did not exist.

The only defect is that the control does not declare it computes and records
the planted signal's presence in both groups before recovery is read.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 0.05, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": false,
#                "records_both_groups": false},
#   "readings": [{"name": "detector_recovery", "depends_on_effect": true}],
#   "comparability": {"model": "pythia-70m-deduped",
#                      "hook": "blocks.3.hook_resid_post",
#                      "threshold": 0.8, "n": 1500, "correction": "BH q=0.10"}
# }
# END-GATE-DECL

import numpy as np


def run_positive_control(planted, groups):
    # recovery is read directly; presence of the planted signal is never checked
    return float(sum(1 for g in groups if planted in g)) / max(len(groups), 1)

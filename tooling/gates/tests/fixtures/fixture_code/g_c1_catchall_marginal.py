"""FAILING fixture for G-C1 — catch-all groups with marginal 1.0.

Drawn from DEC-019 failure 1 (run 1): groups chosen as top-activation features
on the signal text, which at pythia-70m fire on ~2000/2000 background samples.
Injecting into more rows cannot raise a marginal already at 1.0, so the NPMI
statistic stays structurally below its 0.8 threshold at any injection rate.

The only defect is the declared marginal p_x = 1.0.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 1.0, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": true,
#                "records_both_groups": true},
#   "readings": [{"name": "detector_recovery", "depends_on_effect": true}],
#   "comparability": {"model": "pythia-70m-deduped",
#                      "hook": "blocks.3.hook_resid_post",
#                      "threshold": 0.8, "n": 2000, "correction": "BH q=0.10"}
# }
# END-GATE-DECL

import numpy as np

"""FAILING fixture for G-C5 — cross-run incomparable parameters.

Two numbers can only be compared when the parameters that would make the
comparison meaningless are matched (Maith PIPELINE_QUALITY_GATES G5-4). Here the
comparability block names the model but omits the hook, threshold, n and
correction — so a reading from this run is not comparable to any other.

The only defect is the incomplete `comparability` object.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 0.05, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": true,
#                "records_both_groups": true},
#   "readings": [{"name": "detector_recovery", "depends_on_effect": true}],
#   "comparability": {"model": "pythia-70m-deduped"}
# }
# END-GATE-DECL

import numpy as np

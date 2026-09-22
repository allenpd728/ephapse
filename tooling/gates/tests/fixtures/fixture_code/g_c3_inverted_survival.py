"""FAILING fixture for G-C3 — an inverted survival function.

Drawn from DEC-019 failure 4 (runs 1-4): the per-pair p-value used
`gammaincc(k, lambda)`, the regularized *lower* incomplete gamma with the
arguments reversed, which returns 1.0 for every pair. No pair could be
significant; the only reason detection appeared to fire was that the NPMI mask
alone was being counted.

The defect is the `gammaincc` call — there is no GATE-DECL binding asserting
its direction, and gammaincc is not an upper tail.
"""

# GATE-DECL
# {
#   "statistic": {"name": "npmi", "p_x": 0.05, "p_y": 0.04,
#                  "rate": 0.20, "threshold": 0.8},
#   "control": {"computes_planted_presence": true,
#                "records_both_groups": true},
#   "readings": [{"name": "detector_recovery", "depends_on_effect": true}],
#   "comparability": {"model": "pythia-70m-deduped",
#                      "hook": "blocks.3.hook_resid_post",
#                      "threshold": 0.8, "n": 1500, "correction": "BH q=0.10"}
# }
# END-GATE-DECL

from scipy.special import gammaincc


def pair_pvalue(k: int, lam: float) -> float:
    return float(gammaincc(k, lam))

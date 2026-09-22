#!/usr/bin/env python3
"""Single source for the gate-count figures (issue #38).

Three figures circulated in prose (37, 38, "7 wired") and disagreed with the
registry. The spec's own § 3 inventory table is the authority — it enumerates
the gate ids — so the count is derived from it here rather than hand-copied.
Prose that quotes a count should cite this module's output, not a typed number.

Usage:
    python3 tooling/gates/gate_inventory.py           # human summary
    python3 tooling/gates/gate_inventory.py --json     # machine-readable
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SPEC = REPO / "docs" / "reference" / "TEST_VALIDATION_SPEC.md"

# A row of the § 3 inventory: | **G-P1** | description | provenance | tier |
_ROW = re.compile(r"^\|\s*\*\*(G-[A-Z]\d+)\*\*\s*\|(.*)\|\s*([0-9/]+)\s*\|\s*$")


def counts(spec_path: Path = SPEC) -> dict:
    """Derive the totals from the spec inventory table.

    `tier` is the spec's own column: "0" is tier-0 only, "1" is tier-1 only,
    and "0/1" marks a gate that is tier-0 capable but conditionally needs more
    (G-P2, the tokenizer-level check). `tier0` counts every id that can run at
    tier 0, which is why G-P2 is included.
    """
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in spec_path.read_text().splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        gid, tier = m.group(1), m.group(3)
        if gid in seen:  # duplicates would be a spec defect, not a count
            continue
        seen.add(gid)
        rows.append((gid, tier))

    tiers = {"0": 0, "1": 0, "0/1": 0}
    for _, tier in rows:
        tiers[tier] = tiers.get(tier, 0) + 1

    return {
        "total": len(rows),
        "tier0": tiers["0"] + tiers["0/1"],
        "tier1": tiers["1"],
        "tier0_only": tiers["0"],
        "conditional": tiers["0/1"],
        "ids": [gid for gid, _ in rows],
    }


def main() -> int:
    c = counts()
    if "--json" in sys.argv:
        print(json.dumps(c, indent=2))
        return 0
    print(f"specified gate ids: {c['total']}")
    print(f"tier-0 capable:     {c['tier0']}  (of which {c['conditional']} conditional)")
    print(f"tier-1 only:        {c['tier1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared test setup for the tier-0 gate suite (issue #9).

Puts `tooling/gates/` on sys.path so the gate modules can `from run_all import
Gate, register`, matching how `run_all.py` loads them at run time.
"""
from __future__ import annotations

import sys
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent.parent
REPO = GATES_DIR.parent.parent

if str(GATES_DIR) not in sys.path:
    sys.path.insert(0, str(GATES_DIR))

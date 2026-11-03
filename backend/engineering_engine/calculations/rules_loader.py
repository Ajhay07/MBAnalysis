"""Loads engineering_engine/rules/manufacturing_rules.json once and exposes it as a plain
dict - the single source of truth for every configurable allowance, so a calculator never has
a magic number (10, 100, 15, 250, 3.14...) written directly into its own code. Changing an
allowance means editing the JSON, not the calculators."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "manufacturing_rules.json"


@lru_cache(maxsize=1)
def load_rules() -> dict:
    with open(_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

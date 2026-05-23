"""Output hygiene for the judges.

Two jobs:
1. Strip every long dash from any emitted string and replace it with a hyphen,
   so no em dash ever reaches the knowledge base, the dashboard, or a commit.
2. Coerce model numbers into clean unit scores in the range 0 to 1.

Judges output JSON only, no em dashes in any field.
"""
from __future__ import annotations

from typing import Any

# Every long dash variant maps to a plain hyphen. The product rule is hyphens
# only. The characters are built from code points with chr() so this source file
# contains no literal long dash and passes the repo lint, while the replacement
# still strips the real characters at runtime. Covered: em dash, en dash,
# horizontal bar, figure dash, minus sign, non breaking hyphen.
_DASH_CODEPOINTS = (0x2014, 0x2013, 0x2015, 0x2012, 0x2212, 0x2011)
_DASHES = {chr(cp): "-" for cp in _DASH_CODEPOINTS}


def _clean_str(value: str) -> str:
    for bad, good in _DASHES.items():
        if bad in value:
            value = value.replace(bad, good)
    return value


def no_em_dashes(obj: Any) -> Any:
    """Recursively replace every long dash with a hyphen in all strings."""
    if isinstance(obj, str):
        return _clean_str(obj)
    if isinstance(obj, list):
        return [no_em_dashes(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(no_em_dashes(item) for item in obj)
    if isinstance(obj, dict):
        return {no_em_dashes(k): no_em_dashes(v) for k, v in obj.items()}
    return obj


def unit(value: Any) -> float:
    """Coerce a value into a unit score in the range 0 to 1, rounded to 4 places.

    Non numeric input becomes 0.0. This guards every sub-score so the JudgeScores
    shape always validates even when a model returns junk.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN guard
        return 0.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return round(number, 4)


def mean(values: "list[float]") -> float:
    """Mean of a list of unit scores, 0.0 when empty."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def as_str(value: Any, default: str = "") -> str:
    """Coerce to a clean string with no long dashes."""
    if value is None:
        return default
    return _clean_str(str(value))


def as_str_list(value: Any) -> "list[str]":
    """Coerce to a list of clean strings, dropping empties."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    out = []
    for item in items:
        text = as_str(item).strip()
        if text:
            out.append(text)
    return out

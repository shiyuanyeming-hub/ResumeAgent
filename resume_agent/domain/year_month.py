"""Year-month value helpers for resume periods."""

import re

YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def is_year_month(value: str) -> bool:
    """Return True when value matches YYYY-MM (lexicographic == chronological)."""
    return bool(YEAR_MONTH_RE.fullmatch(value))


def year_month_le(start: str, end: str) -> bool:
    """Compare two YYYY-MM strings; raises ValueError on invalid input."""
    if not is_year_month(start) or not is_year_month(end):
        raise ValueError("year_month_le requires valid YYYY-MM strings")
    return start <= end

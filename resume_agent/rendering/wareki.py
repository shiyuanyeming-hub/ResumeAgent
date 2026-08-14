"""Japanese era (和暦) conversion with day-precision boundaries.

The authoritative copy used by the rendering layer so that exported
Japanese resumes carry era years (令和/平成/昭和/大正/明治) instead of
western years. The browser workbench keeps a JS mirror for its date tool.
"""

from __future__ import annotations

import re

# (era, start year/month/day). Day precision keeps 1989-01 and 1926-12
# in their previous eras, matching Japanese resume conventions.
ERA_RULES: list[tuple[str, tuple[int, int, int]]] = [
    ("令和", (2019, 5, 1)),
    ("平成", (1989, 1, 8)),
    ("昭和", (1926, 12, 25)),
    ("大正", (1912, 7, 30)),
    ("明治", (1868, 10, 23)),
]

ERA_START_YEAR = {"令和": 2019, "平成": 1989, "昭和": 1926, "大正": 1912, "明治": 1868}

_ISO_MONTH = re.compile(r"^\d{4}-\d{2}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def to_wareki(year: int, month: int = 1, day: int = 1) -> str:
    """Convert (year, month, day) to a 和暦 string, e.g. 令和6年7月1日."""
    if (year, month, day) < (1868, 10, 23):
        return f"{year}年{month}月{day}日"
    for era, (sy, sm, sd) in ERA_RULES:
        if (year, month, day) >= (sy, sm, sd):
            era_year = year - ERA_START_YEAR[era] + 1
            if era_year > 1:
                return f"{era}{era_year}年{month}月{day}日"
            return f"{era}元年{month}月{day}日"
    return f"{year}年{month}月{day}日"


def to_wareki_date(iso: str) -> str:
    """Convert an ISO date string to 和暦.

    ``2024-07-01`` → ``令和6年7月1日``; ``2024-07`` → ``令和6年7月``.
    Non-ISO values are returned unchanged so free-form dates pass through.
    """
    if not iso:
        return ""
    if _ISO_DATE.match(iso):
        year, month, day = (int(part) for part in iso.split("-"))
        return to_wareki(year, month, day)
    if _ISO_MONTH.match(iso):
        year, month = (int(part) for part in iso.split("-"))
        return to_wareki(year, month).replace("1日", "")
    return iso


def from_wareki(text: str) -> str | None:
    """Convert a 和暦 string back to ISO ``YYYY-MM-DD``; ``None`` if invalid."""
    match = re.match(
        r"(令和|平成|昭和|大正|明治)(?:(\d{1,3})|元)年(\d{1,2})月(?:(\d{1,2})日)?",
        (text or "").strip(),
    )
    if not match:
        return None
    era = match.group(1)
    era_year = 1 if match.group(2) is None else int(match.group(2))
    month = int(match.group(3))
    day = int(match.group(4)) if match.group(4) else 1
    year = ERA_START_YEAR[era] + era_year - 1

    for index, (name, (sy, sm, sd)) in enumerate(ERA_RULES):
        if name != era:
            continue
        next_start = ERA_RULES[index - 1][1] if index > 0 else (9999, 12, 31)
        if (year, month, day) < (sy, sm, sd) or (year, month, day) >= next_start:
            return None
        break
    return f"{year:04d}-{month:02d}-{day:02d}"

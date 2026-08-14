"""Tests for the 和暦 (Japanese era) conversion module."""

import pytest

from resume_agent.rendering.wareki import from_wareki, to_wareki, to_wareki_date


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2024, 7, 1, "令和6年7月1日"),
        (2019, 5, 1, "令和元年5月1日"),
        (2019, 4, 30, "平成31年4月30日"),
        (1989, 1, 8, "平成元年1月8日"),
        (1989, 1, 7, "昭和64年1月7日"),
        (1926, 12, 25, "昭和元年12月25日"),
        (1926, 12, 24, "大正15年12月24日"),
        (1912, 7, 30, "大正元年7月30日"),
        (1868, 10, 23, "明治元年10月23日"),
    ],
)
def test_to_wareki_era_boundaries(year, month, day, expected):
    assert to_wareki(year, month, day) == expected


def test_to_wareki_date_full_and_month_precision():
    assert to_wareki_date("2024-07-01") == "令和6年7月1日"
    assert to_wareki_date("2024-07") == "令和6年7月"
    assert to_wareki_date("2019-04") == "平成31年4月"
    assert to_wareki_date("2019-05") == "令和元年5月"
    assert to_wareki_date("1989-01") == "昭和64年1月"


def test_to_wareki_date_passes_through_freeform_values():
    assert to_wareki_date("") == ""
    assert to_wareki_date("2024年7月") == "2024年7月"
    assert to_wareki_date("Summer 2024") == "Summer 2024"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("令和6年7月1日", "2024-07-01"),
        ("令和元年5月1日", "2019-05-01"),
        ("平成31年4月30日", "2019-04-30"),
        ("昭和64年1月7日", "1989-01-07"),
    ],
)
def test_from_wareki_round_trips(text, expected):
    assert from_wareki(text) == expected


def test_from_wareki_rejects_out_of_era_range():
    # 平成 begins 1989-01-08; 平成元年1月1日 is not a valid 平成 date.
    assert from_wareki("平成元年1月1日") is None
    assert from_wareki("令和元年1月1日") is None  # 令和 begins 2019-05-01
    assert from_wareki("不存在的日期") is None

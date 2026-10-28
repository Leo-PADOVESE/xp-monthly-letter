from datetime import date

from core import periods


def test_case_month_matches_the_readme_dates():
    p = periods.from_folder("2025-05")
    assert (p.letter_date, p.start, p.end, p.key) == (date(2025, 5, 7), date(2025, 3, 31), date(2025, 4, 30), "2025-04")
    assert periods.from_key("2025-04") == p


def test_reference_month_rolls_over_the_year_and_skips_weekends():
    p = periods.from_key("2025-12")
    assert p.folder == "2026-01" and p.end == date(2025, 12, 31) and p.start == date(2025, 11, 28)
    assert periods.from_key("2025-08").end == date(2025, 8, 29)  # 30-31/08/2025 is a weekend
    assert [x.key for x in periods.recent(date(2025, 10, 15), 2)] == ["2025-09", "2025-08"]

"""Letter months.

A client's month folder is named after the month the letter goes out (data/clients/<slug>/2025-05).
The letter is dated day 7 of that month and covers the previous calendar month (the reference
month), from the close of the last business day of the month before it to the close of the last
business day of the reference month. For the case: folder 2025-05, letter on 07/05/2025, April 2025
from 31/03 to 30/04.

The XP macro research of each reference month is kept in data/macro/<yyyy-mm>.pdf.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACRO_DIR = ROOT / "data" / "macro"
LETTER_DAY = 7


def last_business_day(year: int, month: int) -> date:
    day = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _shift(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + months
    return index // 12, index % 12 + 1


@dataclass(frozen=True)
class Period:
    reference: date      # first day of the reference month
    letter_date: date
    start: date
    end: date

    @property
    def folder(self) -> str:
        return f"{self.letter_date:%Y-%m}"

    @property
    def key(self) -> str:
        return f"{self.reference:%Y-%m}"

    @property
    def macro_report(self) -> Path:
        return MACRO_DIR / f"{self.key}.pdf"


def from_reference(year: int, month: int) -> Period:
    letter_year, letter_month = _shift(year, month, 1)
    return Period(date(year, month, 1), date(letter_year, letter_month, LETTER_DAY),
                  last_business_day(*_shift(year, month, -1)), last_business_day(year, month))


def from_key(key: str) -> Period:
    """From the reference month, e.g. "2025-09" (September letters, sent in October)."""
    year, month = map(int, key.split("-"))
    return from_reference(year, month)


def from_folder(folder: str) -> Period:
    """From a client month folder name, e.g. "2025-05" (the letters of April)."""
    year, month = map(int, folder.split("-"))
    return from_reference(*_shift(year, month, -1))


def recent(today: date | None = None, count: int = 24) -> list[Period]:
    """The last closed reference months, newest first."""
    today = today or date.today()
    return [from_reference(*_shift(today.year, today.month, -i)) for i in range(1, count + 1)]

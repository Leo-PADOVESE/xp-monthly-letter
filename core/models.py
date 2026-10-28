"""Domain models shared by every module of the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

# Asset classes used across profitability, recommendation and the letter.
STOCKS = "stocks"
FUNDS = "funds"
FIXED_INCOME = "fixed_income"
CASH = "cash"


@dataclass
class Position:
    """A single holding as reported in the client's statement."""

    asset_class: str            # stocks | funds | fixed_income
    sub_class: str              # e.g. equity, fixed_income_fund, multimarket, bank_deposit
    name: str                   # ticker for stocks, full name for funds and bonds
    market_value: float         # R$ at the snapshot date
    allocation_pct: float       # % of total invested, as reported by the statement
    cumulative_return_pct: float | None = None  # since the investment date, as reported
    investment_date: date | None = None
    # Stocks
    quantity: int | None = None
    average_price: float | None = None
    last_price: float | None = None
    # Funds
    invested_amount: float | None = None
    net_value: float | None = None
    quota_date: date | None = None
    # Fixed income
    rate: str | None = None
    application_date: date | None = None
    maturity_date: date | None = None


@dataclass
class Portfolio:
    """Structured version of a client's monthly statement."""

    client_name: str
    account: str
    snapshot_at: datetime
    advisor_code: str
    advisor_name: str
    total_equity: float         # invested + cash
    total_invested: float
    cash_available: float
    positions: list[Position] = field(default_factory=list)
    class_totals: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def by_class(self, asset_class: str) -> list[Position]:
        return [p for p in self.positions if p.asset_class == asset_class]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        """Inverse of ``to_dict`` (portfolio.json written by the ingestion step)."""
        dates = ("investment_date", "quota_date", "application_date", "maturity_date")
        positions = [Position(**{k: date.fromisoformat(v) if k in dates and v else v for k, v in p.items()})
                     for p in data["positions"]]
        fields = {k: v for k, v in data.items() if k != "positions"}
        fields["snapshot_at"] = datetime.fromisoformat(fields["snapshot_at"])
        return cls(positions=positions, **fields)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value

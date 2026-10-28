from datetime import date, datetime

import pytest

from core.history import build, month_ends, since_purchase
from core.models import Portfolio, Position
from core.profitability import AssetReturn


class FlatSource:
    """Every asset earns 1% a month."""

    def asset_return(self, position, start, end):
        return AssetReturn(None, None, 0.01, "test")


def portfolio(first_investment: date) -> Portfolio:
    positions = [
        Position("stocks", "equity", "AAAA3", 1000.0, 50.0, investment_date=first_investment,
                 quantity=10, average_price=80.0),
        Position("funds", "fixed_income_fund", "Fundo RF", 1000.0, 50.0, investment_date=date(2020, 1, 2),
                 invested_amount=900.0),
    ]
    return Portfolio("Ana", "1", datetime(2025, 5, 7), "A1", "Assessor", 2000.0, 2000.0, 0.0, positions)


def flat_benchmarks(start, end):
    return {"CDI": 0.01, "IBOV": 0.0, "IPCA": 0.005}


def test_twelve_months_of_a_flat_portfolio_compound():
    history = build(portfolio(date(2020, 1, 2)), FlatSource(), date(2025, 4, 30), {"CDI": 1.0}, flat_benchmarks)
    assert history["months"] == 12 and history["start"] == "2024-04-30"
    assert history["total"]["portfolio"] == pytest.approx((1.01 ** 12 - 1) * 100)
    assert history["total"]["PROFILE"] == pytest.approx(history["total"]["CDI"])
    # The result in reais over the window: today's value minus the value walked back 12 months.
    assert history["total"]["gain_brl"] == pytest.approx(2000 - 2000 / 1.01 ** 12)


def test_a_young_portfolio_starts_at_its_first_investment():
    young = Portfolio("Ana", "1", datetime(2025, 5, 7), "A1", "Assessor", 1000.0, 1000.0, 0.0,
                      [Position("stocks", "equity", "AAAA3", 1000.0, 100.0, investment_date=date(2025, 1, 15))])
    ends = month_ends(young, date(2025, 4, 30))
    assert ends[0] == date(2025, 1, 15) and ends[-1] == date(2025, 4, 30)
    history = build(young, FlatSource(), date(2025, 4, 30), {"CDI": 1.0}, flat_benchmarks)
    assert history["since_first_investment"] and history["months"] == 4


def test_since_purchase_uses_average_price_and_invested_amount():
    result = since_purchase(portfolio(date(2020, 1, 2)))
    assert result["cost"] == 800.0 + 900.0 and result["value"] == 2000.0

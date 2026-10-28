from pathlib import Path

import pytest

from core.ingestion import (
    IngestionError,
    parse_number,
    parse_risk_profile_label,
    parse_xp_portfolio,
    pdf_to_text,
)
from core.models import FIXED_INCOME, FUNDS, STOCKS

ALBERT = Path(__file__).resolve().parents[1] / "data" / "clients" / "albert_da_silva"


@pytest.fixture(scope="module")
def albert():
    return parse_xp_portfolio(pdf_to_text(ALBERT / "2025-05" / "portfolio.pdf"))


@pytest.mark.parametrize("raw, expected", [
    ("R$386,858.82", 386858.82),
    ("R$ 30.000,00", 30000.00),
    ("R$ 29,05", 29.05),
    ("-41,7%", -41.7),
    ("8.91%", 8.91),
    ("R$305.44", 305.44),
    ("1642", 1642.0),
])
def test_parse_number_handles_us_and_br_notation(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


def test_header_totals(albert):
    assert albert.client_name == "Albert da Silva"
    assert albert.account == "792854"
    assert albert.advisor_code == "A7699"
    assert albert.advisor_name == "Antonio Bicudo"
    assert albert.total_equity == pytest.approx(386858.82)
    assert albert.cash_available == pytest.approx(74672.62)


def test_positions_by_class(albert):
    assert [p.name for p in albert.by_class(STOCKS)] == ["LREN3", "MRFG3", "ARZZ3", "HAPV3"]
    assert len(albert.by_class(FUNDS)) == 7
    assert len(albert.by_class(FIXED_INCOME)) == 1
    assert sum(p.market_value for p in albert.positions) == pytest.approx(albert.total_invested)


def test_detail_columns_are_merged_in_order(albert):
    lren3 = albert.by_class(STOCKS)[0]
    assert (lren3.quantity, lren3.last_price, lren3.average_price) == (1642, 16.94, 29.05)
    cdb = albert.by_class(FIXED_INCOME)[0]
    assert cdb.rate == "IPC-A +5,45%"
    assert cdb.maturity_date.isoformat() == "2024-09-05"


def test_data_quality_warnings(albert):
    joined = " ".join(albert.warnings)
    assert "matured on 2024-09-05" in joined
    assert "Cash is 19.3%" in joined


def test_risk_profile_label():
    assert parse_risk_profile_label(pdf_to_text(ALBERT / "risk_profile.pdf")) == "moderate"


def test_missing_file_fails_loudly(tmp_path):
    with pytest.raises(IngestionError):
        pdf_to_text(tmp_path / "missing.pdf")

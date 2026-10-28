"""The parser must handle any client in the XP layout, not only the case's client."""

import pytest

from core.ingestion import parse_risk_profile_label, parse_xp_portfolio, pdf_to_text
from core.models import FIXED_INCOME, FUNDS, STOCKS
from scripts import make_sample_statement as sample

BASE = {
    "name": "Cliente Teste", "account": "123456", "snapshot": "07/05/2025 18:40",
    "advisor_code": "A7699", "advisor_name": "Antonio Bicudo", "cash": 8500.0,
    "risk_profile": {"label": "Arrojado", "paragraphs": ["Texto do perfil."]},
}
STOCK_ROWS = [
    {"ticker": t, "quantity": q, "average_price": avg, "last_price": last, "investment_date": "12/05/2021"}
    for t, q, avg, last in [("PETR4", 1200, 30.15, 31.02), ("VALE3", 500, 68.90, 53.40), ("WEGE3", 400, 38.70, 44.10),
                            ("PRIO3", 900, 22.40, 37.85), ("ITUB4", 1000, 25.10, 35.80)]
]
FUND_ROWS = [
    {"name": "Kapitalo Kappa Advisory FIC FIM", "invested": 40000.0, "net_value": 44880.15,
     "investment_date": "05/06/2023", "quota_date": "06/05/2025"},
    {"name": "SPX Nimitz Feeder FIC FIM", "invested": 35000.0, "net_value": 37210.40,
     "investment_date": "05/06/2023", "quota_date": "06/05/2025"},
    {"name": "Dynamo Cougar FIC FIA", "invested": 30000.0, "net_value": 33712.90,
     "investment_date": "18/07/2023", "quota_date": "06/05/2025"},
]
BOND_ROWS = [
    {"name": "CDB BANCO XP S.A. - JAN/2027", "value": 104532.18, "invested": 90000.0, "rate": "102% CDI",
     "investment_date": "20/01/2024", "application_date": "20/01/2024", "maturity_date": "20/01/2027"},
]


def roundtrip(spec, tmp_path):
    model = sample.build(spec)
    sample.render_statement(model, tmp_path / "portfolio.pdf")
    return model, parse_xp_portfolio(pdf_to_text(tmp_path / "portfolio.pdf"))


def test_five_stocks_and_three_funds(tmp_path):
    model, p = roundtrip({**BASE, "stocks": STOCK_ROWS, "funds": FUND_ROWS}, tmp_path)
    assert [x.name for x in p.by_class(STOCKS)] == ["PETR4", "VALE3", "WEGE3", "PRIO3", "ITUB4"]
    assert len(p.by_class(FUNDS)) == 3 and not p.by_class(FIXED_INCOME)
    assert p.total_invested == pytest.approx(model["invested"]) and p.cash_available == 8500.0
    assert p.by_class(STOCKS)[0].quantity == 1200 and p.by_class(STOCKS)[0].last_price == 31.02
    assert p.by_class(FUNDS)[2].sub_class == "equity_fund"
    assert p.client_name == "Cliente Teste" and p.account == "123456"
    assert not [w for w in p.warnings if "subtotal" in w or "quantity" in w]


def test_statement_without_stocks_keeps_subtotals_aligned(tmp_path):
    _, p = roundtrip({**BASE, "funds": FUND_ROWS, "bonds": BOND_ROWS}, tmp_path)
    assert set(p.class_totals) == {FUNDS, FIXED_INCOME}
    assert p.class_totals[FIXED_INCOME] == pytest.approx(104532.18)
    assert p.by_class(FIXED_INCOME)[0].rate == "102% CDI"


def test_risk_profile_document(tmp_path):
    sample.render_risk_profile(BASE, tmp_path / "risk_profile.pdf")
    assert parse_risk_profile_label(pdf_to_text(tmp_path / "risk_profile.pdf")) == "aggressive"


def test_unknown_section_stops_with_a_clear_error(tmp_path):
    from core.ingestion import IngestionError
    model = sample.build({**BASE, "stocks": STOCK_ROWS})
    model["sections"].append(("Tesouro Direto", [{"name": "Tesouro Selic 2029", "value": 1000.0, "invested": 900.0,
                                                  "alloc": 1.0, "return": 11.1, **BOND_ROWS[0]}]))
    sample.render_statement(model, tmp_path / "portfolio.pdf")
    with pytest.raises(IngestionError, match="Tesouro Direto"):
        parse_xp_portfolio(pdf_to_text(tmp_path / "portfolio.pdf"))

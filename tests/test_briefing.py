import json
from pathlib import Path

import pytest

from core.briefing import brl, class_contribution, formatted_results, pct, pct_of_cdi, portfolio_facts, pp
from core.ingestion import parse_xp_portfolio, pdf_to_text
from core.letter_ai import check_numbers

ALBERT = Path(__file__).resolve().parents[1] / "data" / "clients" / "albert_da_silva" / "2025-05"


@pytest.fixture(scope="module")
def albert():
    portfolio = parse_xp_portfolio(pdf_to_text(ALBERT / "portfolio.pdf"))
    report = json.loads((ALBERT / "profitability_market.json").read_text(encoding="utf-8"))
    return portfolio, report


def test_brazilian_formats():
    assert brl(14711.97) == "R$ 14.711,97"
    assert brl(-6771.5) == "-R$ 6.771,50"
    assert pct(3.9512) == "+3,95%" and pct(19.3, signed=False) == "19,30%"
    assert pp(2.9) == "+2,90 p.p."


def test_highlights_separate_best_performer_from_top_contributor(albert):
    _, report = albert
    h = formatted_results(report)["highlights"]
    assert h["best_performer"]["asset"] == "ARZZ3"      # +29.96%, priced as AZZA3
    assert h["top_contributor"]["asset"] == "LREN3"     # largest gain in R$, larger weight
    assert h["assets_with_negative_return"] == []


def test_portfolio_facts_for_albert(albert):
    portfolio, report = albert
    facts = {f["id"]: f for f in portfolio_facts(portfolio, report, "moderate")["facts"]}
    assert "R$ 74.672,62" in facts["idle_cash"]["fact"]
    assert any(k.startswith("matured:CDB BANCO C6") for k in facts)
    assert {"concentration:Riza Lotus Plus Advisory FIC FIRF REF DI CP",
            "concentration:Brave I FIC FIM CP"} <= set(facts)
    assert "Brave I FIC FIM CP" in facts["data_proxy"]["fact"]


def test_number_check_flags_figures_not_in_the_data(albert):
    _, report = albert
    results = formatted_results(report)
    letter = {"performance_pt": ["A carteira rendeu 3,95% no mês, contra +1,06% do CDI, e ganhou R$ 14.711,97.",
                                 "LREN3 subiu 21,30% no período."]}
    assert check_numbers(letter, results) == ["21,30%"]


def test_number_check_compares_values_not_spelling():
    facts = {"fact": "acima de 15,00% em um único ativo", "cash": "R$ 74.672,62"}
    letter = {"performance_pt": ["Concentração acima de 15% e saldo de R$ 74.672,62."]}
    assert check_numbers(letter, facts) == []


def test_fund_types_split_the_funds_class(albert):
    _, report = albert
    types = {t["type"]: t for t in formatted_results(report)["fund_types"]}
    assert set(types) == {"Fundos de renda fixa", "Fundos multimercado", "Fundos de ações"}
    assert "Truxt Long Bias Advisory FIC FIM" in types["Fundos de ações"]["funds"]


def test_class_contribution_adds_up_to_the_portfolio_return(albert):
    _, report = albert
    rows = class_contribution(report)
    assert sum(r["contribution_pp"] for r in rows) == pytest.approx(report["return_pct"], abs=0.01)
    assert rows[0]["class"] == "Ações"
    assert formatted_results(report)["formatted"]["return_as_pct_of_cdi"] == "374% do CDI"


def test_pct_of_cdi_only_when_both_positive(albert):
    _, report = albert
    assert pct_of_cdi({**report, "return_pct": -1.0}) is None

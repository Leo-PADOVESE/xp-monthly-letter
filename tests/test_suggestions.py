import json
from pathlib import Path

import pytest

from core.briefing import portfolio_facts
from core.ingestion import parse_xp_portfolio, pdf_to_text
from core.letter_ai import check_suggestions
from core.suggestions import candidates

CLIENTS = Path(__file__).resolve().parents[1] / "data" / "clients"


def options_for(client: str, profile: str) -> list[dict]:
    month = CLIENTS / client / "2025-05"
    portfolio = parse_xp_portfolio(pdf_to_text(month / "portfolio.pdf"))
    report = json.loads((month / "profitability_market.json").read_text(encoding="utf-8"))
    return candidates(portfolio, report, portfolio_facts(portfolio, report, profile), profile)


@pytest.mark.parametrize("client,profile,expected", [
    ("albert_da_silva", "moderate", {"idle_cash", "matured:CDB BANCO C6 CONSIGNADO S.A. - SET/2024"}),
    ("bruno_tavares", "aggressive", {"no_fixed_income", "stocks_drawdown"}),
])
def test_candidates_follow_the_facts(client, profile, expected):
    ids = {o["id"] for o in options_for(client, profile)}
    assert expected <= ids


def test_aggressive_client_never_gets_more_individual_stocks():
    actions = " ".join(o["action_pt"] for o in options_for("bruno_tavares", "aggressive"))
    assert "ampliar posições individuais" in actions and "Aumentar" not in actions


def test_check_suggestions():
    options = [{"id": "idle_cash", "type": "opportunity"}, {"id": "no_fixed_income", "type": "protection"}]
    ok = {"suggestions": [{"candidate_id": "idle_cash", "type": "opportunity"},
                          {"candidate_id": "no_fixed_income", "type": "protection"}]}
    assert check_suggestions(ok, options) == []
    bad = {"suggestions": [{"candidate_id": "commodities", "type": "opportunity"},
                           {"candidate_id": "no_fixed_income", "type": "opportunity"}]}
    assert check_suggestions(bad, options) == ["sugestão fora das candidatas: commodities",
                                               "tipo trocado em no_fixed_income"]

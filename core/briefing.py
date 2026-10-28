"""What the Rivet agent receives about a client: formatted results and portfolio facts.

The agent writes the analysis and the assessment, but it never calculates. Everything it may
quote is prepared here, already in Brazilian format ("+3,95%", "R$ 14.711,97"), so the letter
copies figures instead of re-deriving them, and ``letter_ai.check_numbers`` can verify that every
figure in the letter exists in this briefing.

Portfolio facts are objective observations the attention points must be anchored in (idle cash,
matured bonds, class weights, concentration); they are not recommendations by themselves.
"""

from __future__ import annotations

from datetime import date

from core.models import CASH, FIXED_INCOME, FUNDS, STOCKS, Portfolio

CONCENTRATION_LIMIT_PCT = 15.0    # a single fund or stock above this share of total equity
IDLE_CASH_LIMIT_PCT = 2.0         # cash above this share of total equity (its opportunity cost is worth a line)

CLASS_LABELS_PT = {
    STOCKS: "Ações", "equity_fund": "Fundos de ações", "multimarket_fund": "Fundos multimercado",
    "fixed_income_fund": "Fundos de renda fixa", "other_fund": "Outros fundos",
    FIXED_INCOME: "Renda fixa (CDB)", CASH: "Saldo em conta", FUNDS: "Fundos (todos os tipos)",
}
PROFILE_PT = {"conservative": "Conservador", "moderate": "Moderado", "aggressive": "Arrojado"}
MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro"]


# --------------------------------------------------------------------- formats

def brl(value: float) -> str:
    """R$ 14.711,97 (negative: -R$ 1.234,56)."""
    text = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"-R$ {text}" if value < 0 else f"R$ {text}"


def pct(value: float, signed: bool = True) -> str:
    """+3,95% (always two decimals)."""
    text = f"{value:+.2f}" if signed else f"{value:.2f}"
    return text.replace(".", ",") + "%"


def pp(value: float) -> str:
    return f"{value:+.2f}".replace(".", ",") + " p.p."


def month_pt(day: date) -> str:
    return f"{MONTHS_PT[day.month - 1]} de {day.year}"


# -------------------------------------------------------------------- briefing

def _class_key(position: dict) -> str:
    return position["sub_class"] if position["asset_class"] == FUNDS else position["asset_class"]


def _fund_types(report: dict) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for p in report["positions"]:
        if p["asset_class"] == FUNDS:
            groups.setdefault(p["sub_class"], []).append(p)
    rows = []
    for sub_class, funds in groups.items():
        start, end = sum(f["start_value"] for f in funds), sum(f["end_value"] for f in funds)
        rows.append({"type": CLASS_LABELS_PT.get(sub_class, sub_class), "funds": [f["name"] for f in funds],
                     "weight": pct(sum(f["weight_pct"] for f in funds), signed=False),
                     "return": pct((end / start - 1) * 100)})
    return rows


def class_contribution(report: dict) -> list[dict]:
    """Where the month's result came from: contribution of each class (funds by type) in R$ and p.p."""
    groups: dict[str, list[dict]] = {}
    for p in report["positions"]:
        groups.setdefault(_class_key(p), []).append(p)
    rows = [{"class": CLASS_LABELS_PT.get(key, key), "contribution_brl": sum(p["contribution_brl"] for p in ps),
             "contribution_pp": sum(p["contribution_pp"] for p in ps)} for key, ps in groups.items()]
    return sorted(rows, key=lambda r: -r["contribution_brl"])


def formatted_history(history: dict) -> dict:
    """The consolidated window (12 months, or since the first investment) with quotable figures."""
    total, since = history["total"], history.get("since_purchase")
    start, end = date.fromisoformat(history["start"]), date.fromisoformat(history["end"])
    out = {
        "window": (f"desde a primeira aplicação, de {start:%d/%m/%Y} a {end:%d/%m/%Y}" if history["since_first_investment"]
                   else f"últimos {history['months']} meses, de {start:%d/%m/%Y} a {end:%d/%m/%Y}"),
        "portfolio": pct(total["portfolio"]),
        **({"gain": brl(total["gain_brl"])} if "gain_brl" in total else {}),
        "cdi": pct(total["CDI"]), "ibovespa": pct(total["IBOV"]),
        "inflation_ipca15": pct(total["IPCA"]), "profile_benchmark": pct(total["PROFILE"]),
        "excess_vs_cdi": pp(total["portfolio"] - total["CDI"]),
        "how_it_was_built": history["note"],
    }
    if since:
        out["since_purchase"] = {"invested": brl(since["cost"]), "current_value": brl(since["value"]),
                                 "result": brl(since["gain_brl"]), "return": pct(since["return_pct"]),
                                 **({"first_investment": f"{date.fromisoformat(since['first_investment']):%d/%m/%Y}"}
                                    if since.get("first_investment") else {}),
                                 "basis": "preço médio das ações e valor aplicado nos fundos e títulos, "
                                          "contra o valor atual do extrato"}
    return out


def _class_status(c: dict, report: dict, matured: set[str], no_return: dict) -> str | None:
    """Cash, or a class made only of matured bonds, has no return of the month to quote."""
    if c["asset_class"] == CASH:
        return no_return["cash"]
    names = [p["name"] for p in report["positions"] if p["asset_class"] == c["asset_class"]]
    return no_return["matured"] if names and all(n in matured for n in names) else None


def formatted_results(report: dict) -> dict:
    """The profitability report with every quotable figure pre-formatted."""
    invested = [p for p in report["positions"] if p["asset_class"] != CASH]
    # A matured bond earns 0% by definition; it is a fact to act on, not a "worst performer".
    ranked = [p for p in invested if "matured" not in p.get("note", "")] or invested
    by_return = sorted(ranked, key=lambda p: p["monthly_return_pct"], reverse=True)
    by_contribution = sorted(ranked, key=lambda p: p["contribution_brl"], reverse=True)
    bench = report["benchmarks_pct"]
    matured = {p["name"] for p in invested if "matured" in p.get("note", "")}
    # Cash and a matured bond show 0,00% by construction. Quoted as a number, the writer kept picking the
    # matured CDB as "o menor retorno do mês", so they reach the agent as a status, not as a return.
    no_return = {"cash": "não se aplica (saldo sem rendimento)",
                 "matured": "vencido: já pago, não é resultado do mês (valor disponível para reinvestir)"}

    def status(p: dict) -> str | None:
        return no_return["cash"] if p["asset_class"] == CASH else no_return["matured"] if p["name"] in matured else None

    def position_row(p: dict) -> dict:
        row = {"asset": p["name"], "class": CLASS_LABELS_PT.get(_class_key(p), p["asset_class"]),
               "weight": pct(p["weight_pct"], signed=False), "value_end": brl(p["end_value"]),
               "return": status(p) or pct(p["monthly_return_pct"]), "contribution": brl(p["contribution_brl"]),
               "contribution_pp": pp(p["contribution_pp"])}
        # Data caveats (proxies, matured bonds) reach the agent as portfolio facts, in Portuguese.
        return row

    return {
        # "% do CDI" was dropped: on a month driven by stocks it read as a fixed income yield ("374% do CDI").
        "scope": "Tudo em 'results', exceto 'consolidated_window', é do mês de referência apenas; "
                 "'consolidated_window' é o acumulado da janela de 12 meses (ou desde a primeira aplicação).",
        "period": f"{month_pt(date.fromisoformat(report['period_end']))} "
                  f"(fechamento de {date.fromisoformat(report['period_start']):%d/%m/%Y} "
                  f"a {date.fromisoformat(report['period_end']):%d/%m/%Y})",
        "formatted": {
            "portfolio_return": pct(report["return_pct"]),
            "portfolio_return_invested_only": pct(report["return_invested_pct"]),
            "gain": brl(report["gain_brl"]),
            "equity_end": brl(report["total_end"]),
            "cdi": pct(bench["CDI"]),
            "ibovespa": pct(bench["IBOV"]),
            "inflation_ipca15": pct(bench["IPCA"]),
            "profile_benchmark": pct(bench["PROFILE"]),
            "excess_vs_cdi": pp(report["excess_vs_cdi_pp"]),
            "excess_vs_profile_benchmark": pp(report["excess_vs_profile_pp"]),
            "real_return": pct(report["real_return_pct"]),
            "cash_opportunity_cost": brl(report["cash_opportunity_cost_brl"]),
        },
        "highlights": {
            "best_performer": {"asset": by_return[0]["name"], "return": pct(by_return[0]["monthly_return_pct"])},
            "worst_performer": {"asset": by_return[-1]["name"], "return": pct(by_return[-1]["monthly_return_pct"])},
            "top_contributor": {"asset": by_contribution[0]["name"],
                                "contribution": brl(by_contribution[0]["contribution_brl"])},
            "bottom_contributor": {"asset": by_contribution[-1]["name"],
                                   "contribution": brl(by_contribution[-1]["contribution_brl"])},
            "assets_with_negative_return": [p["name"] for p in invested if p["monthly_return_pct"] < 0],
        },
        # Funds appear only by type: the all-funds return mixes equity, multimarket and fixed income funds,
        # and the writer kept quoting it as "fundos de ações" (+4,32% instead of the equity fund's +12,20%).
        "classes": [{"class": CLASS_LABELS_PT.get(c["asset_class"], c["asset_class"]),
                     "weight": pct(c["weight_pct"], signed=False),
                     "return": _class_status(c, report, matured, no_return) or pct(c["monthly_return_pct"])}
                    for c in report["classes"] if c["asset_class"] != FUNDS],
        "fund_types": _fund_types(report),
        # Attribution: which classes produced the month's result (the per-asset detail is in "positions").
        "class_contribution": [{"class": r["class"], "contribution": brl(r["contribution_brl"]),
                                "contribution_pp": pp(r["contribution_pp"])}
                               for r in class_contribution(report) if abs(r["contribution_brl"]) >= 0.5],
        "positions": [position_row(p) for p in report["positions"]],
    }


def portfolio_facts(portfolio: Portfolio, report: dict, profile: str) -> dict:
    """Objective facts about the portfolio, each with an id the attention points can cite."""
    equity = portfolio.total_equity
    facts: list[dict] = []

    weights: dict[str, float] = {}
    for p in portfolio.positions:
        key = p.sub_class if p.asset_class == FUNDS else p.asset_class
        weights[key] = weights.get(key, 0.0) + p.market_value
    weights[CASH] = portfolio.cash_available
    facts.append({"id": "class_weights", "fact": "Peso de cada classe no patrimônio total",
                  "values": {CLASS_LABELS_PT.get(k, k): pct(v / equity * 100, signed=False)
                             for k, v in sorted(weights.items(), key=lambda kv: -kv[1])}})

    cash_share = portfolio.cash_available / equity * 100
    if cash_share > IDLE_CASH_LIMIT_PCT:
        facts.append({"id": "idle_cash",
                      "fact": f"Saldo parado em conta de {brl(portfolio.cash_available)} "
                              f"({pct(cash_share, signed=False)} do patrimônio), sem rendimento",
                      "opportunity_cost_month": brl(report["cash_opportunity_cost_brl"])})

    for p in portfolio.by_class(FIXED_INCOME):
        if p.maturity_date and p.maturity_date < portfolio.snapshot_at.date():
            facts.append({"id": f"matured:{p.name}",
                          "fact": f"{p.name} venceu em {p.maturity_date:%d/%m/%Y} e ainda aparece na carteira "
                                  f"({brl(p.market_value)}); o valor está disponível para reinvestir"})

    for p in portfolio.positions:
        share = p.market_value / equity * 100
        if share > CONCENTRATION_LIMIT_PCT:
            facts.append({"id": f"concentration:{p.name}",
                          "fact": f"{p.name} representa {pct(share, signed=False)} do patrimônio "
                                  f"(acima de {pct(CONCENTRATION_LIMIT_PCT, signed=False)} em um único ativo)"})

    no_fixed_income = not portfolio.by_class(FIXED_INCOME) and not any(
        p.sub_class == "fixed_income_fund" for p in portfolio.positions)
    if no_fixed_income:
        facts.append({"id": "no_fixed_income", "fact": "A carteira não tem renda fixa nem fundos de renda fixa"})

    proxies = [p["name"] for p in report["positions"] if str(p.get("source", "")).startswith("proxy")]
    if proxies:
        facts.append({"id": "data_proxy",
                      "fact": "Rentabilidade estimada por índice de referência (sem cota diária pública): "
                              + ", ".join(proxies)})

    return {"profile": profile, "profile_pt": PROFILE_PT.get(profile, profile),
            "total_equity": brl(equity), "facts": facts}


def client_card(portfolio: Portfolio, profile: str, letter_date: date, period_end: date) -> dict:
    return {
        "name": portfolio.client_name, "first_name": portfolio.client_name.split()[0],
        "account": portfolio.account, "profile_pt": PROFILE_PT.get(profile, profile),
        "advisor_name": portfolio.advisor_name, "advisor_code": portfolio.advisor_code,
        "letter_date": f"{letter_date:%d/%m/%Y}", "reference_month": month_pt(period_end),
    }

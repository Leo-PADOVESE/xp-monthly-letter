"""The portfolio's consolidated performance over the last 12 months (or since its first investment).

The statement is a snapshot: it has today's positions, their average price or invested amount and
the investment dates, but not the movements of the past months. So the history is rebuilt from the
current positions: each one is priced month by month with the same sources as the monthly return
(Yahoo Finance, CVM quotas, the bond's curve) and counted only from its investment date on. The
portfolio return of each month is the value-weighted return of what was held, cash included, and
the months are chained. Deposits and withdrawals of the period are not in the statement, so the
line is a simulation of the current portfolio, and the letter says so.

Benchmarks over the same window: CDI, Ibovespa, inflation (IPCA-15, known on the letter date) and
the profile benchmark. The result since purchase (average price or invested amount against the
current value) comes from the statement itself.

CLI:
    python -m core.history data/clients/albert_da_silva/2025-05
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from core import periods
from core.ingestion import load_portfolio, parse_risk_profile_label, pdf_to_text
from core.models import FIXED_INCOME, FUNDS, STOCKS, Portfolio, Position
from core.profitability import MarketSource, PriceSource, load_settings, market_benchmarks

MONTHS = 12


def month_ends(portfolio: Portfolio, end: date, months: int = MONTHS) -> list[date]:
    """Month-end closes from 12 months before ``end`` (or the first month-end after the first investment)."""
    ends = [periods.last_business_day(*periods._shift(end.year, end.month, -i)) for i in range(months, -1, -1)]
    first = min((p.investment_date for p in portfolio.positions if p.investment_date), default=None)
    if first:
        ends = [d for d in ends if d >= first] or ends[-1:]
        # The first point is the close on or before the first investment, so its first month counts.
        if ends[0] > first and len(ends) <= months:
            ends.insert(0, first)
    return ends


def cost_basis(position: Position) -> float | None:
    """What the client paid: average price x quantity for stocks, the invested amount otherwise."""
    if position.asset_class == STOCKS and position.quantity and position.average_price:
        return position.quantity * position.average_price
    if position.asset_class in (FUNDS, FIXED_INCOME):
        return position.invested_amount
    return None


def since_purchase(portfolio: Portfolio) -> dict | None:
    priced = [(p.market_value, cost_basis(p)) for p in portfolio.positions if cost_basis(p)]
    value, cost = sum(v for v, _ in priced), sum(c for _, c in priced)
    if not cost:
        return None
    return {"cost": cost, "value": value, "gain_brl": value - cost, "return_pct": (value / cost - 1) * 100}


def build(portfolio: Portfolio, source: PriceSource, end: date, profile_weights: dict[str, float],
          benchmarks=market_benchmarks) -> dict:
    ends = month_ends(portfolio, end)
    windows = list(zip(ends, ends[1:]))
    # Monthly return of every position, then its value walked back from today's market value.
    returns = {p.name: [source.asset_return(p, s, e).monthly_return for s, e in windows] for p in portfolio.positions}
    values = {}
    for p in portfolio.positions:
        series = [p.market_value]
        for r in reversed(returns[p.name]):
            series.insert(0, series[0] / (1 + r))
        values[p.name] = series

    def held(p: Position, day: date) -> bool:
        return p.investment_date is None or p.investment_date <= day

    cumulative = {"portfolio": 1.0, "CDI": 1.0, "IBOV": 1.0, "IPCA": 1.0, "PROFILE": 1.0}
    points = [{"date": ends[0].isoformat(), **{k: 0.0 for k in cumulative}}]
    for k, (s, e) in enumerate(windows):
        live = [p for p in portfolio.positions if held(p, s)]
        start_value = sum(values[p.name][k] for p in live) + portfolio.cash_available
        gain = sum(values[p.name][k] * returns[p.name][k] for p in live)
        bench = benchmarks(s, e)
        month = {"portfolio": gain / start_value, **bench,
                 "PROFILE": sum(w * bench[name] for name, w in profile_weights.items())}
        for key in cumulative:
            cumulative[key] *= 1 + month[key]
        points.append({"date": e.isoformat(), **{key: (v - 1) * 100 for key, v in cumulative.items()}})

    first = min((p.investment_date for p in portfolio.positions if p.investment_date), default=ends[0])
    since = since_purchase(portfolio)
    return {
        "start": ends[0].isoformat(), "end": ends[-1].isoformat(), "months": len(windows),
        "since_first_investment": first >= ends[0],
        "points": points, "total": points[-1],
        "since_purchase": since and {**since, "first_investment": first.isoformat()},
        "note": "Simulação com as posições atuais do extrato e as cotações históricas de cada ativo, a partir da "
                "data de aplicação; aportes e resgates do período não constam do extrato.",
    }


def run(month_dir: Path) -> dict:
    settings = load_settings()
    profile = parse_risk_profile_label(pdf_to_text(month_dir.parent / "risk_profile.pdf"))
    portfolio = load_portfolio(month_dir)
    period = periods.from_folder(month_dir.name)
    history = build(portfolio, MarketSource(settings.get("ticker_map")), period.end, settings["benchmarks"][profile])
    (month_dir / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the portfolio's last 12 months against its benchmarks")
    parser.add_argument("month_dir", type=Path)
    args = parser.parse_args()
    total = run(args.month_dir)["total"]
    print(", ".join(f"{k} {v:+.2f}%" for k, v in total.items() if k != "date"))


if __name__ == "__main__":
    main()

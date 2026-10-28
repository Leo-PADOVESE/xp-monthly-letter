"""Data for the platform's Macro page: market indices (Yahoo Finance) and rates (Banco Central),
over the 12 months up to the end of a reference month. Every series is cached like the
profitability data, so the page only downloads once per month."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from core import market_data

# Name -> Yahoo tickers to try in order (IFIX has no stable index ticker on Yahoo; XFIX11 tracks it).
INDICES = {"Ibovespa": ["^BVSP"], "IFIX": ["IFIX.SA", "XFIX11.SA"], "Dólar": ["BRL=X"]}
SGS_SELIC_TARGET = 432
SGS_IPCA_12M = 13522


def window(end: date, months: int = 12) -> tuple[date, date]:
    return end - timedelta(days=round(months * 30.44)), end


def index_series(name: str, start: date, end: date) -> pd.Series | None:
    for ticker in INDICES[name]:
        try:
            series = market_data.stock_history(ticker, start, end)
            return series[series.index <= pd.Timestamp(end)].rename(name)
        except Exception:  # noqa: BLE001 - a missing index only hides its chart
            continue
    return None


def month_change(series: pd.Series, start: date, end: date) -> float | None:
    try:
        return market_data.price_on(series, end) / market_data.price_on(series, start) - 1
    except market_data.MarketDataError:
        return None


def rate_series(code: int, start: date, end: date, name: str) -> pd.Series | None:
    try:
        return market_data.sgs_series(code, start, end).rename(name)
    except Exception:  # noqa: BLE001
        return None

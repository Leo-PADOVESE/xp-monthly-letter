"""External market data with a local cache.

Sources
- Stocks and Ibovespa: Yahoo Finance (``yfinance``), adjusted close (includes dividends).
- Investment funds: CVM open data, daily report (quota value per fund CNPJ).
- CDI, IPCA and IPCA-15: Banco Central do Brasil, SGS API (series 12, 433 and 7478).

Every download is cached under ``data/cache`` so the workflow runs offline and
reproducibly after the first execution.

CLI helpers:
    python -m core.market_data find-fund "Riza Lotus"
    python -m core.market_data resolve-funds data/clients/<client>/<yyyy-mm>/portfolio.json --date 2025-04-30
"""

from __future__ import annotations

import argparse
import io
import json
import time
import warnings
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from core import fund_resolver

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
FUND_REGISTRY = ROOT / "config" / "fund_registry.json"

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"
CVM_DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
CVM_REGISTRY_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
CVM_CLASS_REGISTRY_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
SGS_CDI, SGS_IPCA15 = 12, 7478
IBOV = "^BVSP"


class MarketDataError(RuntimeError):
    pass


def _cache(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


# ------------------------------------------------------------------ Yahoo Finance

def _silence_yfinance_warnings() -> None:
    """yfinance still uses pandas' deprecated ``inplace=``; hide that library noise only."""
    warnings.filterwarnings("ignore", message=".*inplace keyword.*", module="yfinance")


def yahoo_ticker(ticker: str) -> str:
    """B3 tickers need the .SA suffix on Yahoo; indices start with ^ and currencies end with =X."""
    return ticker if ticker.startswith("^") or "." in ticker or "=" in ticker else f"{ticker}.SA"


def stock_history(ticker: str, start: date, end: date) -> pd.Series:
    """Daily adjusted close between ``start`` and ``end`` (inclusive)."""
    path = _cache(f"yahoo_{ticker.replace('^', 'IDX_')}_{start}_{end}.csv")
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]

    import yfinance as yf  # imported lazily so offline tests do not need it

    _silence_yfinance_warnings()

    # Pad the window so the first and last trading days are always included.
    data = yf.download(yahoo_ticker(ticker), start=start - timedelta(days=7), end=end + timedelta(days=1),
                       auto_adjust=True, progress=False)
    if data.empty:
        raise MarketDataError(f"Yahoo Finance returned no data for {ticker}")
    close = data["Close"]
    series = (close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close).rename(ticker)
    series.to_csv(path)
    return series


def price_point(series: pd.Series, day: date) -> tuple[date, float]:
    """Last available (date, price) on or before ``day`` (handles weekends and holidays)."""
    available = series[series.index <= pd.Timestamp(day)]
    if available.empty:
        raise MarketDataError(f"No price for {series.name} on or before {day}")
    return available.index[-1].date(), float(available.iloc[-1])


def price_on(series: pd.Series, day: date) -> float:
    return price_point(series, day)[1]


def stock_return(ticker: str, start: date, end: date) -> tuple[float, float]:
    series = stock_history(ticker, start, end)
    return price_on(series, start), price_on(series, end)


def stock_close_raw(ticker: str, start: date, end: date) -> pd.Series:
    """Unadjusted daily close, as shown on Yahoo's and B3's price history pages.

    Used only for manual validation: Yahoo still restates it for later splits and
    reverse splits (e.g. HAPV3 15:1 in June 2025), so it can differ from what traded.
    """
    path = _cache(f"yahoo_raw_{ticker.replace('^', 'IDX_')}_{start}_{end}.csv")
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]

    import yfinance as yf

    _silence_yfinance_warnings()
    data = yf.download(yahoo_ticker(ticker), start=start - timedelta(days=7), end=end + timedelta(days=1),
                       auto_adjust=False, progress=False)
    if data.empty:
        raise MarketDataError(f"Yahoo Finance returned no data for {ticker}")
    close = data["Close"]
    series = (close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close).rename(ticker)
    series.to_csv(path)
    return series


# ------------------------------------------------------------- Banco Central (SGS)

def _get_json(url: str, params: dict, attempts: int = 4) -> list:
    """The Banco Central API fails on and off (timeouts, 502, empty bodies): retry with backoff."""
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    return []


def sgs_series(series: int, start: date, end: date) -> pd.Series:
    path = _cache(f"sgs_{series}_{start}_{end}.json")
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        rows = _get_json(SGS_URL.format(series=series),
                         {"formato": "json", "dataInicial": f"{start:%d/%m/%Y}", "dataFinal": f"{end:%d/%m/%Y}"})
        path.write_text(json.dumps(rows), encoding="utf-8")
    if not rows:
        raise MarketDataError(f"SGS series {series} returned no data for {start}..{end}")
    index = pd.to_datetime([r["data"] for r in rows], format="%d/%m/%Y")
    return pd.Series([float(r["valor"]) for r in rows], index=index, name=f"sgs_{series}")


def cdi_return(start: date, end: date) -> float:
    """Compounded CDI over the period. SGS 12 is the daily rate in % per day.

    The rate published for day D accrues from D to D+1, so the end date is excluded.
    """
    daily = sgs_series(SGS_CDI, start, end)
    daily = daily[(daily.index >= pd.Timestamp(start)) & (daily.index < pd.Timestamp(end))]
    return float((1 + daily / 100).prod() - 1)


def ipca_for_period(start: date, end: date) -> float:
    """Inflation (decimal) for the month that ends the period, as known on the letter date.

    The full IPCA for month M is published around the 10th of M+1, after a letter sent in
    the first days of M+1 (April 2025's IPCA came out on 2025-05-09, the letter is dated
    2025-05-07). IPCA-15 for month M (SGS 7478) is published within M, so it is used to
    avoid look-ahead.
    """
    month = pd.Timestamp(end.replace(day=1))
    series = sgs_series(SGS_IPCA15, month.date(), end)
    if month not in series.index:
        raise MarketDataError(f"IPCA-15 for {month:%Y-%m} not available")
    return float(series[month]) / 100


# ------------------------------------------------------------------ CVM fund data

def fund_registry() -> dict[str, dict]:
    """Statement fund name -> {"cnpj": ...} or {"proxy": "CDI" | "IBOV", "note": ...}.

    Filled automatically by ``fund_entry`` (see ``core.fund_resolver``) and curated with
    ``find-fund`` when a match needs review. A proxy is used, and disclosed in the letter's data
    notes, when a fund (often an XP "Advisory" feeder) is not in the CVM open data.
    """
    if not FUND_REGISTRY.exists():
        return {}
    return json.loads(FUND_REGISTRY.read_text(encoding="utf-8"))


def format_cnpj(value) -> str:
    """CVM files mix "43917493000131" and "43.917.493/0001-31"; use the punctuated form."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) != 14:
        return str(value)
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def cvm_daily_report(yyyymm: str) -> pd.DataFrame:
    path = _cache(f"cvm_inf_diario_{yyyymm}.csv")
    if path.exists():
        frame = pd.read_csv(path, dtype=str)
        frame["CNPJ"] = frame["CNPJ"].map(format_cnpj)
        return frame
    response = requests.get(CVM_DAILY_URL.format(yyyymm=yyyymm), timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with archive.open(archive.namelist()[0]) as handle:
            frame = pd.read_csv(handle, sep=";", dtype=str, encoding="latin-1")
    # Since CVM Resolution 175 the CNPJ column is CNPJ_FUNDO_CLASSE; older files use CNPJ_FUNDO.
    cnpj_col = "CNPJ_FUNDO_CLASSE" if "CNPJ_FUNDO_CLASSE" in frame.columns else "CNPJ_FUNDO"
    frame = frame.rename(columns={cnpj_col: "CNPJ"})[["CNPJ", "DT_COMPTC", "VL_QUOTA"]]
    frame["CNPJ"] = frame["CNPJ"].map(format_cnpj)
    frame.to_csv(path, index=False)
    return frame


def fund_quota_point(cnpj: str, day: date) -> tuple[date, float]:
    """(date, quota value) on or before ``day``."""
    months = {day.strftime("%Y%m"), (day.replace(day=1) - timedelta(days=1)).strftime("%Y%m")}
    frames = [cvm_daily_report(m) for m in sorted(months)]
    frame = pd.concat(frames)
    rows = frame[(frame["CNPJ"] == cnpj) & (frame["DT_COMPTC"] <= day.isoformat())]
    if rows.empty:
        raise MarketDataError(f"No CVM quota for fund {cnpj} on or before {day}")
    last = rows.sort_values("DT_COMPTC").iloc[-1]
    return date.fromisoformat(last["DT_COMPTC"]), float(last["VL_QUOTA"])


def _registry_frames() -> list[pd.DataFrame]:
    """CVM fund registers, normalised to CNPJ / NAME / STATUS / SOURCE columns.

    Since CVM Resolution 175 active funds and their classes live in the new
    ``registro_fundo_classe.zip``; the legacy ``cad_fi.csv`` mostly lists cancelled funds.
    Both are searched so older feeder funds are still found.
    """
    new_path = _cache("cvm_registro_fundo_classe.zip")
    if not new_path.exists():
        response = requests.get(CVM_CLASS_REGISTRY_URL, timeout=300)
        response.raise_for_status()
        new_path.write_bytes(response.content)
    old_path = _cache("cvm_cad_fi.csv")
    if not old_path.exists():
        response = requests.get(CVM_REGISTRY_URL, timeout=300)
        response.raise_for_status()
        old_path.write_bytes(response.content)

    raw: list[tuple[str, pd.DataFrame]] = []
    with zipfile.ZipFile(new_path) as archive:
        for member in archive.namelist():
            with archive.open(member) as handle:
                raw.append((member, pd.read_csv(handle, sep=";", dtype=str, encoding="latin-1")))
    raw.append(("cad_fi.csv", pd.read_csv(old_path, sep=";", dtype=str, encoding="latin-1")))

    frames = []
    for source, frame in raw:
        columns = {c.lower(): c for c in frame.columns}
        name = next((columns[c] for c in columns if c.startswith("denom")), None)
        cnpj = next((columns[c] for c in columns if c.startswith("cnpj")), None)
        status = next((columns[c] for c in columns if c.startswith("sit")), None)
        if name and cnpj:
            frames.append(pd.DataFrame({
                "CNPJ": frame[cnpj].map(format_cnpj),
                "NAME": frame[name].fillna("").str.upper(),
                "STATUS": frame[status] if status else "",
                "SOURCE": source,
            }))
    return frames


def find_fund(query: str) -> pd.DataFrame:
    """Search the CVM registers by name, to fill config/fund_registry.json."""
    words = fund_resolver.normalize(query)   # accent-insensitive: "Capitania" finds "CAPITÂNIA"
    registry = pd.concat(_registry_frames(), ignore_index=True)
    mask = registry["NAME"].apply(lambda name: all(w in fund_resolver.normalize(name) for w in words))
    result = registry[mask].drop_duplicates(subset=["CNPJ", "NAME"])
    # Active funds first.
    return result.sort_values("STATUS", key=lambda s: ~s.fillna("").str.upper().str.contains("FUNCIONAMENTO"))


def fund_has_quotas(cnpj: str, day: date) -> bool:
    """True when the CVM daily report of ``day``'s month has quotas for ``cnpj``."""
    return bool((cvm_daily_report(day.strftime("%Y%m"))["CNPJ"] == cnpj).any())


def fund_entry(name: str, sub_class: str, day: date) -> tuple[dict, str]:
    """Registry entry for a statement fund, resolving and saving new names automatically.

    Returns (entry, warning). The warning is empty for curated funds and tells the advisor
    to confirm a fund that was matched automatically or priced by proxy."""
    registry = fund_registry()
    entry = registry.get(name)
    if entry is None:
        frame = pd.concat(_registry_frames(), ignore_index=True)
        resolution = fund_resolver.resolve(name, sub_class, frame, lambda cnpj: fund_has_quotas(cnpj, day))
        registry[name] = entry = resolution.entry
        fund_resolver.save_registry(FUND_REGISTRY, registry)
        return entry, resolution.warning
    if entry.get("status") == "needs_review":
        return entry, f"{name}: {entry.get('note', 'priced by proxy')}; confirm the CNPJ in config/fund_registry.json"
    return entry, ""


def resolve_funds(portfolio_json: Path, day: date) -> list[str]:
    """Resolve every fund of a parsed statement up front (onboarding a client)."""
    data = json.loads(portfolio_json.read_text(encoding="utf-8"))
    messages = []
    for position in data["positions"]:
        if position["asset_class"] == "funds":
            entry, warning = fund_entry(position["name"], position.get("sub_class", ""), day)
            messages.append(warning or f"{position['name']}: {entry.get('cnpj') or 'proxy ' + entry.get('proxy', '?')}")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description="Market data helpers")
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("find-fund", help="Search the CVM registry by name")
    find.add_argument("query")
    resolve = sub.add_parser("resolve-funds", help="Map every fund of a parsed statement to a CNPJ")
    resolve.add_argument("portfolio_json", type=Path)
    resolve.add_argument("--date", type=date.fromisoformat, required=True,
                         help="period end, used to check the fund publishes daily quotas")
    args = parser.parse_args()
    if args.command == "resolve-funds":
        for message in resolve_funds(args.portfolio_json, args.date):
            print(message)
    if args.command == "find-fund":
        with pd.option_context("display.max_colwidth", 100, "display.width", 200):
            print(find_fund(args.query).to_string(index=False))


if __name__ == "__main__":
    main()

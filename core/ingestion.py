"""Turn client PDFs into clean text and structured data.

Rivet cannot read PDFs, so every client document goes through this module first:

1. ``pdf_to_text`` extracts the text page by page with pdfplumber, which keeps table
   rows on a single line (the .txt files shipped with the case lost that structure).
   Scanned PDFs fall back to OCR when pytesseract is installed.
2. ``parse_xp_portfolio`` reads the XP statement layout into a ``Portfolio``.
3. ``validate_portfolio`` reconciles every total so bad inputs never reach the LLM.

CLI:
    python -m core.ingestion data/clients/albert_da_silva/2025-05/portfolio.pdf
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from core.models import FIXED_INCOME, FUNDS, STOCKS, Portfolio, Position

SECTION_HEADERS = {
    "Ações": STOCKS,
    "Fundos de Investimentos": FUNDS,
    "Renda Fixa": FIXED_INCOME,
}

MONEY = r"R\$\s?-?[\d.,]+"
DATE = r"\d{2}/\d{2}/\d{4}"

ASSET_ROW = re.compile(rf"^(?P<name>.+?) (?P<value>{MONEY}) (?P<alloc>-?[\d.,]+)% (?P<third>.+)$")
STOCK_DETAIL = re.compile(rf"^(?P<date>{DATE}) (?P<avg>{MONEY}) (?P<last>{MONEY}) (?P<qty>\d+)$")
FUND_DETAIL = re.compile(rf"^(?P<date>{DATE}) (?P<invested>{MONEY}) (?P<net>{MONEY}) (?P<quota>{DATE})$")
BOND_DETAIL = re.compile(rf"^(?P<date>{DATE}) (?P<rate>.+?) (?P<applied>{DATE}) (?P<maturity>{DATE})$")
SUBTOTAL = re.compile(rf"^(?P<value>{MONEY})$")


class IngestionError(ValueError):
    """Raised when a document cannot be read or does not match the expected layout."""


# --------------------------------------------------------------------------- text

def pdf_to_text(path: str | Path) -> str:
    """Extract text from a PDF, one block per page, with OCR fallback for scans."""
    path = Path(path)
    if not path.exists():
        raise IngestionError(f"File not found: {path}")
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                text = _ocr_page(page)
            pages.append(f"<<page {number}>>\n{text.strip()}")
    text = "\n\n".join(pages)
    if not re.sub(r"<<page \d+>>", "", text).strip():
        raise IngestionError(f"No text could be extracted from {path}")
    return text


def _ocr_page(page: pdfplumber.page.Page) -> str:
    try:
        import pytesseract  # optional dependency, only needed for scanned documents
    except ImportError:
        return ""
    image = page.to_image(resolution=300).original
    return pytesseract.image_to_string(image, lang="por")


# ------------------------------------------------------------------------ numbers

def parse_number(raw: str) -> float:
    """Parse BRL amounts and percentages written in either US or BR notation.

    The XP statement mixes both: ``R$386,858.82`` and ``R$ 30.000,00``.
    The last separator is the decimal one, unless it groups thousands (``30.000``).
    """
    s = raw.replace("R$", "").replace("%", "").replace(" ", "").strip()
    negative = s.startswith("-")
    s = s.lstrip("-")
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
    elif "," in s:
        decimal = None if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else ","
    elif "." in s:
        decimal = None if re.fullmatch(r"\d{1,3}(\.\d{3})+", s) else "."
    else:
        decimal = None
    thousands = {",": ".", ".": ",", None: ",."}[decimal]
    for sep in thousands:
        s = s.replace(sep, "")
    if decimal == ",":
        s = s.replace(",", ".")
    if not s:
        raise IngestionError(f"Not a number: {raw!r}")
    value = float(s)
    return -value if negative else value


def parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%d/%m/%Y").date()


# ---------------------------------------------------------------------- portfolio

def classify_fund(name: str) -> str:
    """Map a Brazilian fund name to a sub-class using its regulatory suffix."""
    upper = name.upper()
    if re.search(r"\bFIA\b|LONG BIAS|LONG BIASED", upper):
        return "equity_fund"
    if re.search(r"\bFIRF\b|\bRF\b|\bREF DI\b", upper):
        return "fixed_income_fund"
    if re.search(r"\bFIM\b", upper):
        return "multimarket_fund"
    return "other_fund"


def parse_xp_portfolio(text: str) -> Portfolio:
    """Parse the text of an XP "este é o seu patrimônio" statement.

    The PDF prints a wide table split in two halves: the first pages hold
    name / position / allocation / return, the last pages hold the remaining
    columns (dates, prices, quantities) in the same row order.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("<<page")]

    header_idx = next((i for i, ln in enumerate(lines) if "este é o seu patrimônio" in ln), None)
    if header_idx is None:
        raise IngestionError("Statement header ('este é o seu patrimônio') not found")
    client_name = lines[header_idx].split(", este é o seu patrimônio")[0].strip()
    totals = re.findall(MONEY, lines[header_idx + 1])
    if len(totals) != 3:
        raise IngestionError("Expected total equity, total invested and cash on the header line")
    total_equity, total_invested, cash = (parse_number(t) for t in totals)

    account_idx = next((i for i, ln in enumerate(lines) if ln.startswith("Conta:")), None)
    if account_idx is None:
        raise IngestionError("Account line ('Conta: ...') not found")
    left, right = lines[header_idx + 2:account_idx], lines[account_idx:]

    positions, class_share = _parse_left_half(left)
    account, snapshot_at, advisor_code, advisor_name, details, subtotals = _parse_right_half(right)
    _merge_details(positions, details)

    portfolio = Portfolio(
        client_name=client_name,
        account=account,
        snapshot_at=snapshot_at,
        advisor_code=advisor_code,
        advisor_name=advisor_name,
        total_equity=total_equity,
        total_invested=total_invested,
        cash_available=cash,
        positions=positions,
        # Subtotals are printed only for the sections the statement has, in section order.
        class_totals=dict(zip([c for c in (STOCKS, FUNDS, FIXED_INCOME) if any(p.asset_class == c for p in positions)],
                              subtotals)),
    )
    portfolio.warnings = validate_portfolio(portfolio, class_share)
    return portfolio


def _parse_left_half(lines: list[str]) -> tuple[list[Position], dict[str, float]]:
    positions: list[Position] = []
    class_share: dict[str, float] = {}
    current: str | None = None
    for i, line in enumerate(lines):
        if line in SECTION_HEADERS:
            current = SECTION_HEADERS[line]
            if i + 1 < len(lines) and lines[i + 1].endswith("%"):
                class_share[current] = parse_number(lines[i + 1])
            continue
        # A section title is a bare line followed by its share of the portfolio ("19.32%").
        next_is_share = i + 1 < len(lines) and re.fullmatch(r"-?[\d.,]+%", lines[i + 1])
        if next_is_share and not ASSET_ROW.match(line) and not line.startswith("Posição"):
            raise IngestionError(f"Statement section {line!r} is not supported yet "
                                 f"(known: {', '.join(SECTION_HEADERS)}); the letter was not generated")
        match = ASSET_ROW.match(line)
        if not match or current is None:
            continue
        name = match["name"].strip()
        position = Position(
            asset_class=current,
            sub_class={STOCKS: "equity", FIXED_INCOME: "bank_deposit"}.get(current) or classify_fund(name),
            name=name,
            market_value=parse_number(match["value"]),
            allocation_pct=parse_number(match["alloc"]),
        )
        third = match["third"]
        if current == FIXED_INCOME:
            position.invested_amount = parse_number(third)
        else:
            position.cumulative_return_pct = parse_number(third)
        positions.append(position)
    if not positions:
        raise IngestionError("No positions found in the statement")
    return positions, class_share


def _parse_right_half(lines: list[str]):
    account_match = re.match(r"Conta:\s*(\S+)\s*\|\s*(\d{2}/\d{2}/\d{4}),\s*(\d{2}:\d{2})", lines[0])
    if not account_match:
        raise IngestionError(f"Unexpected account line: {lines[0]!r}")
    account = account_match[1]
    snapshot_at = datetime.strptime(f"{account_match[2]} {account_match[3]}", "%d/%m/%Y %H:%M")

    advisor_code = advisor_name = ""
    details: dict[str, list[re.Match]] = {STOCKS: [], FUNDS: [], FIXED_INCOME: []}
    subtotals: list[float] = []
    for i, line in enumerate(lines[1:], start=1):
        if line.startswith("Código do Assessor") and i + 1 < len(lines):
            advisor_code, _, advisor_name = lines[i + 1].partition(" ")
        elif m := STOCK_DETAIL.match(line):
            details[STOCKS].append(m)
        elif m := FUND_DETAIL.match(line):
            details[FUNDS].append(m)
        elif m := BOND_DETAIL.match(line):
            details[FIXED_INCOME].append(m)
        elif m := SUBTOTAL.match(line):
            subtotals.append(parse_number(m["value"]))
    return account, snapshot_at, advisor_code, advisor_name.strip(), details, subtotals


def _merge_details(positions: list[Position], details: dict[str, list[re.Match]]) -> None:
    for asset_class, rows in details.items():
        targets = [p for p in positions if p.asset_class == asset_class]
        if len(rows) != len(targets):
            raise IngestionError(
                f"{asset_class}: {len(targets)} positions but {len(rows)} detail rows; layout not recognised"
            )
        for position, m in zip(targets, rows):
            position.investment_date = parse_date(m["date"])
            if asset_class == STOCKS:
                position.average_price = parse_number(m["avg"])
                position.last_price = parse_number(m["last"])
                position.quantity = int(m["qty"])
            elif asset_class == FUNDS:
                position.invested_amount = parse_number(m["invested"])
                position.net_value = parse_number(m["net"])
                position.quota_date = parse_date(m["quota"])
            else:
                position.rate = m["rate"].strip()
                position.application_date = parse_date(m["applied"])
                position.maturity_date = parse_date(m["maturity"])


# --------------------------------------------------------------------- validation

def validate_portfolio(portfolio: Portfolio, class_share: dict[str, float] | None = None,
                       tolerance: float = 1.0) -> list[str]:
    """Reconcile totals. Hard inconsistencies raise; soft ones become warnings."""
    positions_sum = sum(p.market_value for p in portfolio.positions)
    if abs(positions_sum - portfolio.total_invested) > tolerance:
        raise IngestionError(
            f"Positions add up to R${positions_sum:,.2f} but total invested is R${portfolio.total_invested:,.2f}"
        )
    if abs(portfolio.total_invested + portfolio.cash_available - portfolio.total_equity) > tolerance:
        raise IngestionError("Total invested + cash does not match total equity")

    warnings: list[str] = []
    for asset_class, subtotal in portfolio.class_totals.items():
        computed = sum(p.market_value for p in portfolio.by_class(asset_class))
        if abs(computed - subtotal) > tolerance:
            warnings.append(f"{asset_class}: positions sum R${computed:,.2f} vs subtotal R${subtotal:,.2f}")

    for p in portfolio.by_class(STOCKS):
        implied = p.quantity * p.last_price
        if abs(implied - p.market_value) > tolerance:
            warnings.append(
                f"{p.name}: quantity x last price = R${implied:,.2f} vs position R${p.market_value:,.2f}"
            )

    snapshot = portfolio.snapshot_at.date()
    stale: list[Position] = []
    for p in portfolio.positions:
        if p.maturity_date and p.maturity_date < snapshot:
            warnings.append(f"{p.name}: matured on {p.maturity_date.isoformat()}, still listed on {snapshot.isoformat()}")
        if p.quota_date and (snapshot - p.quota_date).days > 45:
            stale.append(p)
    if stale:
        dates = sorted({p.quota_date.isoformat() for p in stale})
        warnings.append(f"{len(stale)} funds have quota dates ({', '.join(dates)}) older than 45 days "
                        f"for a {snapshot.isoformat()} snapshot")

    cash_share = portfolio.cash_available / portfolio.total_equity * 100
    if cash_share > 10:
        warnings.append(f"Cash is {cash_share:.1f}% of total equity (allocation % ignores it)")
    return warnings


# ------------------------------------------------------------------ risk profile

RISK_LABELS = {"conservador": "conservative", "moderado": "moderate", "arrojado": "aggressive",
               "agressivo": "aggressive", "sofisticado": "aggressive"}


def parse_risk_profile_label(text: str) -> str:
    """Return the suitability label (conservative / moderate / aggressive) stated in a KYC document."""
    match = re.search(r"Classifica\w+ do Perfil de Investimento:\s*(\w+)", text, flags=re.IGNORECASE)
    if not match or match[1].lower() not in RISK_LABELS:
        raise IngestionError("Risk profile classification not found in the document")
    return RISK_LABELS[match[1].lower()]


# ------------------------------------------------------------------ rivet export

def load_portfolio(month_dir: Path) -> Portfolio:
    """The month's portfolio: portfolio.json when the ingestion step wrote one (it may come from the
    Rivet fallback reader), else the statement PDF read by code."""
    saved = month_dir / "portfolio.json"
    if saved.exists():
        return Portfolio.from_dict(json.loads(saved.read_text(encoding="utf-8")))
    return parse_xp_portfolio(pdf_to_text(month_dir / "portfolio.pdf"))


def portfolio_from_extraction(data: dict) -> Portfolio:
    """Build a Portfolio from the Rivet fallback reader's JSON and run the same reconciliation checks.

    Raises IngestionError when the extracted numbers do not add up, so a misread statement never
    reaches the letter."""
    def number(raw):
        return parse_number(str(raw)) if raw not in (None, "") else None

    def day(raw):
        return parse_date(str(raw)) if raw else None

    positions = []
    for row in data.get("positions", []):
        section = (row.get("section") or "").lower()
        asset_class = (STOCKS if "aç" in section or "acoes" in section else
                       FIXED_INCOME if "renda fixa" in section or "cdb" in section else FUNDS)
        name = row["name"].strip()
        positions.append(Position(
            asset_class=asset_class,
            sub_class={STOCKS: "equity", FIXED_INCOME: "bank_deposit"}.get(asset_class) or classify_fund(name),
            name=name, market_value=number(row["market_value"]), allocation_pct=number(row.get("allocation_pct")) or 0.0,
            cumulative_return_pct=number(row.get("cumulative_return_pct")),
            quantity=int(number(row["quantity"])) if row.get("quantity") else None,
            average_price=number(row.get("average_price")), last_price=number(row.get("last_price")),
            invested_amount=number(row.get("invested_amount")), rate=row.get("rate"),
            maturity_date=day(row.get("maturity_date")),
        ))
    if not positions:
        raise IngestionError("The fallback reader found no positions")
    snapshot = day(data.get("snapshot_date")) or date.today()
    portfolio = Portfolio(
        client_name=data["client_name"], account=data.get("account") or "",
        snapshot_at=datetime.combine(snapshot, datetime.min.time()),
        advisor_code=data.get("advisor_code") or "", advisor_name=data.get("advisor_name") or "",
        total_equity=number(data["total_equity"]), total_invested=number(data["total_invested"]),
        cash_available=number(data["cash_available"]), positions=positions,
    )
    stocks_without_price = [p for p in positions if p.asset_class == STOCKS and not (p.quantity and p.last_price)]
    if stocks_without_price:
        raise IngestionError(f"Fallback reader missed quantity or price for {stocks_without_price[0].name}")
    portfolio.warnings = validate_portfolio(portfolio) + ["Statement read by the AI fallback reader; check it"]
    return portfolio


def portfolio_to_text(portfolio: Portfolio) -> str:
    """Compact, unambiguous text version of the statement for the LLM."""
    lines = [
        f"Client: {portfolio.client_name} | Account: {portfolio.account}",
        f"Snapshot: {portfolio.snapshot_at:%Y-%m-%d %H:%M} | Advisor: {portfolio.advisor_name} ({portfolio.advisor_code})",
        f"Total equity: R${portfolio.total_equity:,.2f} | Invested: R${portfolio.total_invested:,.2f} "
        f"| Cash available: R${portfolio.cash_available:,.2f}",
        "",
        "| Class | Sub-class | Asset | Market value (R$) | % of invested | Return since investment (%) | Investment date |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in portfolio.positions:
        ret = "" if p.cumulative_return_pct is None else f"{p.cumulative_return_pct:.2f}"
        when = p.investment_date.isoformat() if p.investment_date else ""
        lines.append(
            f"| {p.asset_class} | {p.sub_class} | {p.name} | {p.market_value:,.2f} | {p.allocation_pct:.2f} | {ret} | {when} |"
        )
    if portfolio.warnings:
        lines += ["", "Data warnings:"] + [f"- {w}" for w in portfolio.warnings]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert an XP portfolio PDF into JSON and LLM-ready text.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out-dir", type=Path, help="Defaults to the PDF's folder")
    args = parser.parse_args()

    out_dir = args.out_dir or args.pdf.parent
    raw_text = pdf_to_text(args.pdf)
    portfolio = parse_xp_portfolio(raw_text)
    (out_dir / "portfolio_raw.txt").write_text(raw_text, encoding="utf-8")
    (out_dir / "portfolio.json").write_text(json.dumps(portfolio.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "portfolio.txt").write_text(portfolio_to_text(portfolio), encoding="utf-8")
    print(f"{portfolio.client_name}: {len(portfolio.positions)} positions, {len(portfolio.warnings)} warnings")
    for w in portfolio.warnings:
        print(f"  ! {w}")


if __name__ == "__main__":
    main()

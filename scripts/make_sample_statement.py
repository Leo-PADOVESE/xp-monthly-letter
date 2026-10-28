"""Render a sample client in the XP statement layout (portfolio.pdf + risk_profile.pdf).

The case ships a single client. To prove the pipeline is not tailored to him, sample
clients are described in a small YAML file (``data/samples/*.yaml``) and rendered here in
the same layout as ``portfolio.pdf``: the wide table split in two halves (name / position
/ allocation / return first, then dates / prices / quantities), US amounts on the left,
BR amounts on the right, exactly as XP prints them.

Stock "last price" can be left out of the YAML: it is then the real Yahoo close on the
snapshot date, so the statement is consistent with the market data used downstream.

    python -m scripts.make_sample_statement data/samples/carla_mendes.yaml
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
ROWS_PER_PAGE = 22
LINE = 18


# ----------------------------------------------------------------------- formats

def us_money(value: float) -> str:
    return f"R${value:,.2f}"


def br_money(value: float) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def br_pct(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + "%"


def br_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _date(value) -> date:
    return value if isinstance(value, date) else datetime.strptime(str(value), "%d/%m/%Y").date()


# ------------------------------------------------------------------------ model

def market_last_price(ticker: str, day: date) -> float:
    from core import market_data   # only needed when the YAML leaves the price out
    series = market_data.stock_close_raw(ticker, day - timedelta(days=10), day)
    return round(market_data.price_on(series, day), 2)


def build(spec: dict) -> dict:
    """Fill the derived numbers: position values, allocations, returns, totals."""
    snapshot = datetime.strptime(spec["snapshot"], "%d/%m/%Y %H:%M")
    stocks = []
    for s in spec.get("stocks", []):
        last = s.get("last_price") or market_last_price(s["ticker"], snapshot.date())
        stocks.append({**s, "last_price": last, "value": round(s["quantity"] * last, 2),
                       "return": (last / s["average_price"] - 1) * 100})
    funds = [{**f, "value": f["net_value"], "return": (f["net_value"] / f["invested"] - 1) * 100}
             for f in spec.get("funds", [])]
    bonds = [dict(b) for b in spec.get("bonds", [])]
    sections = [(title, rows) for title, rows in
                (("Ações", stocks), ("Fundos de Investimentos", funds), ("Renda Fixa", bonds)) if rows]
    invested = round(sum(r["value"] for _, rows in sections for r in rows), 2)
    for _, rows in sections:
        for r in rows:
            r["alloc"] = r["value"] / invested * 100
    return {"spec": spec, "snapshot": snapshot, "sections": sections, "invested": invested,
            "cash": spec["cash"], "equity": round(invested + spec["cash"], 2)}


# ----------------------------------------------------------------------- render

class Writer:
    """Writes text lines top-down, starting a new page when one is full."""

    def __init__(self, path: Path, pagesize):
        self.pdf = canvas.Canvas(str(path), pagesize=pagesize)
        self.width, self.height = pagesize
        self.y = self.height - 50
        self.rows = 0

    def line(self, cells: list[tuple[float, str]], bold: bool = False, size: int = 10) -> None:
        if self.rows >= ROWS_PER_PAGE:
            self.page()
        self.pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        for x, text in cells:
            self.pdf.drawString(x, self.y, text)
        self.y -= LINE
        self.rows += 1

    def page(self) -> None:
        self.pdf.showPage()
        self.y, self.rows = self.height - 50, 0

    def text(self, paragraph: str, size: int = 10, bold: bool = False, width: int = 95) -> None:
        words, current = paragraph.split(), ""
        for word in words:
            if len(current) + len(word) + 1 > width:
                self.line([(60, current)], bold, size)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            self.line([(60, current)], bold, size)

    def save(self) -> None:
        self.pdf.save()


def render_statement(model: dict, path: Path) -> None:
    spec = model["spec"]
    w = Writer(path, landscape(letter))
    first = spec["name"]
    w.line([(40, f"{first}, este é o seu patrimônio"), (430, "Total investido"), (600, "Saldo Disponível")], bold=True)
    w.line([(40, us_money(model["equity"])), (430, us_money(model["invested"])), (600, us_money(model["cash"]))])

    # Left half of the table
    for title, rows in model["sections"]:
        share = sum(r["alloc"] for r in rows)
        w.line([(40, title)], bold=True)
        w.line([(40, f"{share:.2f}%")])
        if title == "Renda Fixa":
            w.line([(40, "Posição a mercado"), (420, "% Alocação"), (560, "Valor aplicado")], bold=True)
        else:
            w.line([(40, "Posição"), (420, "% Alocação"), (560, "Rentabilidade (%)" if title == "Ações" else "Rentabilidade")],
                   bold=True)
        for r in rows:
            name = r.get("ticker") or r["name"]
            third = br_money(r["invested"]) if title == "Renda Fixa" else br_pct(r["return"])
            w.line([(40, name), (330, us_money(r["value"])), (420, f"{r['alloc']:.2f}%"), (560, third)])

    # Right half of the table
    w.page()
    w.line([(40, f"Conta: {spec['account']} | {model['snapshot']:%d/%m/%Y, %H:%M}")], bold=True)
    w.line([(40, "Código do Assessor"), (200, "Nome do assessor")], bold=True)
    w.line([(40, spec["advisor_code"]), (200, spec["advisor_name"])])
    for title, rows in model["sections"]:
        w.line([(40, us_money(round(sum(r["value"] for r in rows), 2)))], bold=True)
        if title == "Ações":
            w.line([(40, "Data do investimento"), (200, "Preço médio"), (330, "Último preço (R$)"), (480, "Qtd. total")], bold=True)
            for r in rows:
                w.line([(40, br_date(_date(r["investment_date"]))), (200, br_money(r["average_price"])),
                        (330, br_money(r["last_price"])), (480, str(r["quantity"]))])
        elif title == "Fundos de Investimentos":
            w.line([(40, "Data do investimento"), (200, "Valor aplicado"), (330, "Valor líquido"), (480, "Data da cota")], bold=True)
            for r in rows:
                w.line([(40, br_date(_date(r["investment_date"]))), (200, br_money(r["invested"])),
                        (330, br_money(r["net_value"])), (480, br_date(_date(r["quota_date"])))])
        else:
            w.line([(40, "Data do investimento"), (200, "Taxa a mercado"), (330, "Data aplicação"), (480, "Data vencimento")], bold=True)
            for r in rows:
                w.line([(40, br_date(_date(r["investment_date"]))), (200, r["rate"]),
                        (330, br_date(_date(r["application_date"]))), (480, br_date(_date(r["maturity_date"])))])
    w.save()


def render_risk_profile(spec: dict, path: Path) -> None:
    profile = spec["risk_profile"]
    w = Writer(path, letter)
    w.text(f"Perfil de Risco do Cliente: {spec['name'].split()[0]}", size=12, bold=True)
    w.text(f"Classificação do Perfil de Investimento: {profile['label']}", bold=True)
    for paragraph in profile["paragraphs"]:
        w.text(paragraph)
    w.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    model = build(spec)
    client_dir = ROOT / "data" / "clients" / slug(spec["name"])
    month_dir = client_dir / f"{model['snapshot']:%Y-%m}"
    month_dir.mkdir(parents=True, exist_ok=True)
    render_statement(model, month_dir / "portfolio.pdf")
    render_risk_profile(spec, client_dir / "risk_profile.pdf")
    print(f"{spec['name']}: equity {us_money(model['equity'])}, invested {us_money(model['invested'])} "
          f"-> {month_dir / 'portfolio.pdf'}")


if __name__ == "__main__":
    main()

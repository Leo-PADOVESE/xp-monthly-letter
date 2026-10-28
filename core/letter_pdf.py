"""Lay out the approved letter as a two-page A4 PDF with charts.

Input: ``letter.json`` (text written by the Rivet agent) and ``profitability_market.json``
(figures computed by ``core.profitability``). The text is placed as written; every figure in
the charts, tiles and table comes from the profitability report, never from the LLM.

Layout
- Header, key figures, greeting, performance, the two charts chosen by the agent and the highlights;
  then macro scenario, suggestions, outlook, closing, results table and disclaimer, flowing over
  the two pages.
If the content does not fit in two pages, the layout is tightened (smaller type and table)
and, failing that, the result is reported so the advisor can ask for a shorter letter.

The PDF can be protected with the first digits of the client's CPF (``password``).

CLI:
    python -m core.letter_pdf data/clients/albert_da_silva/2025-05
"""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from core.briefing import CLASS_LABELS_PT, brl, pct  # noqa: E402

MAX_PAGES = 2

# Palette: XP-inspired black and yellow, neutral greys; green/red only for gains and losses.
INK = colors.HexColor("#141414")
YELLOW = colors.HexColor("#FFC709")
GREY = colors.HexColor("#6B6B6B")
LIGHT = colors.HexColor("#F3F3F3")
RULE = colors.HexColor("#DADADA")
GAIN, LOSS = "#1E8E4E", "#C0392B"
CHART_INK, CHART_YELLOW, CHART_GREY = "#141414", "#FFC709", "#B5B5B5"

DISCLAIMER = (
    "Este material tem caráter informativo e não constitui oferta, solicitação ou recomendação de compra ou venda "
    "de ativos. As sugestões apresentadas são pontos para conversa com o seu assessor e devem ser avaliadas de acordo "
    "com o seu perfil de investidor. Rentabilidade passada não é garantia de rentabilidade futura. "
    "Fontes: posições do extrato XP; preços de ações do Yahoo Finance (fechamento ajustado); cotas de fundos da CVM; "
    "CDI e IPCA-15 do Banco Central; cenário do relatório macro da XP."
)


@dataclass
class Layout:
    body: float = 9.6
    leading: float = 13.2
    chart_height: float = 74 * mm
    table_body: float = 7.6


COMFORTABLE, COMPACT = Layout(), Layout(body=8.9, leading=11.9, chart_height=60 * mm, table_body=7.0)


# --------------------------------------------------------------------- charts

def _figure_to_image(fig, width: float, height: float) -> Image:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=220, bbox_inches="tight", transparent=False, facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    return Image(buffer, width=width, height=height)


def _style_axes(ax) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(CHART_GREY)
    ax.tick_params(colors="#333333", labelsize=7, length=0)
    ax.xaxis.grid(True, color="#EBEBEB", linewidth=0.6)
    ax.set_axisbelow(True)


def _br(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def chart_allocation(report: dict, width: float, height: float) -> Image:
    """Share of total equity by asset class (funds split by type)."""
    shares: dict[str, float] = {}
    for p in report["positions"]:
        key = p["sub_class"] if p["asset_class"] == "funds" else p["asset_class"]
        label = CLASS_LABELS_PT.get(key, key)
        shares[label] = shares.get(label, 0) + p["weight_pct"]
    items = sorted(shares.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    bars = ax.barh([k for k, _ in items], [v for _, v in items], color=CHART_INK, height=0.6)
    bars[-1].set_color(CHART_YELLOW)
    for bar, (_, v) in zip(bars, items):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2, f"{_br(v)}%", va="center", fontsize=7)
    ax.set_xlim(0, max(v for _, v in items) * 1.25)
    ax.set_title("Alocação por classe (% do patrimônio)", fontsize=8.5, loc="left", fontweight="bold")
    _style_axes(ax)
    ax.set_xticks([])
    return _figure_to_image(fig, width, height)


def chart_contribution(report: dict, width: float, height: float) -> Image:
    """Contribution of each asset to the month's result, in R$ (largest movers)."""
    rows = [p for p in report["positions"] if p["asset_class"] != "cash" and abs(p["contribution_brl"]) >= 0.5]
    rows = sorted(rows, key=lambda p: abs(p["contribution_brl"]), reverse=True)[:8]
    rows = sorted(rows, key=lambda p: p["contribution_brl"])
    names = [_short(p["name"], 22) for p in rows]
    values = [p["contribution_brl"] for p in rows]
    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    ax.barh(names, values, color=[GAIN if v >= 0 else LOSS for v in values], height=0.6)
    span = max(abs(v) for v in values) or 1
    for i, v in enumerate(values):
        ax.text(v + (span * 0.03 if v >= 0 else -span * 0.03), i, brl(v).replace("R$ ", "R$"),
                va="center", ha="left" if v >= 0 else "right", fontsize=6.5)
    low, high = min(values + [0]), max(values + [0])
    ax.set_xlim(low - span * 0.7 if low < 0 else 0, high + span * 0.5)
    ax.axvline(0, color=CHART_GREY, linewidth=0.8)
    ax.set_title("Contribuição para o resultado do mês (R$)", fontsize=8.5, loc="left", fontweight="bold")
    _style_axes(ax)
    ax.set_xticks([])
    return _figure_to_image(fig, width, height)


def chart_benchmarks(report: dict, width: float, height: float) -> Image:
    """Portfolio return versus CDI, Ibovespa, inflation and the profile benchmark."""
    bench = report["benchmarks_pct"]
    items = [("Sua carteira", report["return_pct"]), ("Benchmark do perfil", bench["PROFILE"]),
             ("CDI", bench["CDI"]), ("Ibovespa", bench["IBOV"]), ("Inflação (IPCA-15)", bench["IPCA"])]
    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    labels, values = [k for k, _ in items][::-1], [v for _, v in items][::-1]
    bar_colors = [CHART_GREY] * (len(items) - 1) + [CHART_YELLOW if report["return_pct"] >= 0 else LOSS]
    ax.barh(labels, values, color=bar_colors, height=0.6)
    span = max(abs(v) for v in values) or 1
    for i, v in enumerate(values):
        ax.text(v + (span * 0.03 if v >= 0 else -span * 0.03), i, f"{'+' if v >= 0 else ''}{_br(v, 2)}%",
                va="center", ha="left" if v >= 0 else "right", fontsize=7)
    low = min(values + [0])
    ax.set_xlim(low - span * 0.35 if low < 0 else 0, max(values + [0]) + span * 0.35)
    ax.axvline(0, color=CHART_GREY, linewidth=0.8)
    ax.set_title("Rentabilidade no mês: carteira x referências", fontsize=8.5, loc="left", fontweight="bold")
    _style_axes(ax)
    ax.set_xticks([])
    return _figure_to_image(fig, width, height)


CHARTS = {"allocation": chart_allocation, "contribution": chart_contribution, "benchmarks": chart_benchmarks}


# --------------------------------------------------------------------- layout

def _styles(layout: Layout) -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("body", fontName="Helvetica", fontSize=layout.body, leading=layout.leading,
                          textColor=INK, alignment=TA_LEFT, spaceAfter=layout.body * 0.55)
    return {
        "body": base,
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=layout.body + 2.2,
                             leading=layout.body + 5, spaceBefore=layout.body * 0.6, spaceAfter=layout.body * 0.35,
                             keepWithNext=1),
        "small": ParagraphStyle("small", parent=base, fontSize=6.6, leading=8.4, textColor=GREY),
        "tile_label": ParagraphStyle("tl", parent=base, fontSize=7, leading=8.5, textColor=GREY, spaceAfter=0),
        "tile_value": ParagraphStyle("tv", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=15,
                                     spaceAfter=0),
        "tag": ParagraphStyle("tag", parent=base, fontName="Helvetica-Bold", fontSize=6.8, leading=8,
                              textColor=GREY, spaceAfter=1),
        "card_title": ParagraphStyle("ct", parent=base, fontName="Helvetica-Bold", spaceAfter=1.5),
        "cell": ParagraphStyle("cell", parent=base, fontSize=layout.table_body, leading=layout.table_body + 2,
                               spaceAfter=0),
    }


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tiles(report: dict, st: dict, width: float) -> Table:
    bench = report["benchmarks_pct"]
    tiles = [("Rentabilidade no mês", pct(report["return_pct"])), ("Resultado em reais", brl(report["gain_brl"])),
             ("CDI no mês", pct(bench["CDI"])), ("Benchmark do perfil", pct(bench["PROFILE"]))]
    cells = [[Paragraph(label, st["tile_label"]), Paragraph(value, st["tile_value"])] for label, value in tiles]
    table = Table([cells], colWidths=[width / 4] * 4)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("LINEBEFORE", (1, 0), (-1, -1), 2, colors.white),
        ("LINEABOVE", (0, 0), (0, 0), 2.2, YELLOW), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _short(name: str, size: int) -> str:
    """Cut a long asset name at a word boundary: "CDB BANCO BTG PACTUAL S.A. - AGO/2028" -> "CDB BANCO BTG…"."""
    if len(name) <= size:
        return name
    return name[:size].rsplit(" ", 1)[0].rstrip(" -.") + "…"


def _highlights(letter_doc: dict, st: dict, width: float) -> Table:
    """Highlights of the month, from the figures prepared for the agent (never from its text)."""
    results = letter_doc["briefing"]["results"]
    h, f = results["highlights"], results["formatted"]
    tiles = [("Maior alta", h["best_performer"]["asset"], h["best_performer"]["return"]),
             ("Maior queda" if h["worst_performer"]["return"].startswith("-") else "Menor alta",
              h["worst_performer"]["asset"], h["worst_performer"]["return"]),
             ("Maior contribuição", h["top_contributor"]["asset"], h["top_contributor"]["contribution"]),
             ("Retorno real (descontada a inflação)", "Carteira", f["real_return"])]
    name = ParagraphStyle("hn", parent=st["tile_label"], textColor=INK, fontName="Helvetica-Bold", fontSize=8)
    value = ParagraphStyle("hv", parent=st["tile_value"], fontSize=11, leading=13)
    cells = [[Paragraph(label, st["tile_label"]), Paragraph(_esc(_short(asset, 24)), name), Paragraph(val, value)]
             for label, asset, val in tiles]
    table = Table([cells], colWidths=[width / 4] * 4)
    table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _suggestion_cards(letter: dict, st: dict, width: float) -> list:
    tags = {"opportunity": "OPORTUNIDADE", "protection": "PROTEÇÃO"}
    flow = []
    for s in letter.get("suggestions", []):
        accent = YELLOW if s.get("type") == "opportunity" else INK
        content = [Paragraph(tags.get(s.get("type"), "SUGESTÃO"), st["tag"]),
                   Paragraph(_esc(s.get("title_pt", "")), st["card_title"]),
                   Paragraph(_esc(s.get("text_pt", "")), ParagraphStyle("c", parent=st["body"], spaceAfter=0))]
        card = Table([[content]], colWidths=[width])
        card.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, 0), 2.5, accent), ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        flow += [KeepTogether(card), Spacer(1, 4)]
    return flow


def _results_table(report: dict, st: dict, width: float) -> Table:
    header = ["Ativo", "Peso", "Rentab. no mês", "Contribuição"]
    rows = [[Paragraph(f"<b>{h}</b>", st["cell"]) for h in header]]
    positions = sorted(report["positions"], key=lambda p: -p["end_value"])
    for p in positions:
        color = GAIN if p["monthly_return_pct"] > 0 else LOSS if p["monthly_return_pct"] < 0 else "#333333"
        rows.append([Paragraph(_esc(p["name"]), st["cell"]),
                     Paragraph(pct(p["weight_pct"], signed=False), st["cell"]),
                     Paragraph(f'<font color="{color}">{pct(p["monthly_return_pct"])}</font>', st["cell"]),
                     Paragraph(brl(p["contribution_brl"]), st["cell"])])
    rows.append([Paragraph("<b>Total da carteira</b>", st["cell"]), Paragraph("100,00%", st["cell"]),
                 Paragraph(f"<b>{pct(report['return_pct'])}</b>", st["cell"]),
                 Paragraph(f"<b>{brl(report['gain_brl'])}</b>", st["cell"])])
    table = Table(rows, colWidths=[width * 0.52, width * 0.13, width * 0.17, width * 0.18], repeatRows=1)
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK), ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6), ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    return table


def _header_footer(client: dict):
    def draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, height - 22 * mm, width, 22 * mm, stroke=0, fill=1)
        canvas.setFillColor(YELLOW)
        canvas.rect(0, height - 22 * mm, 4 * mm, 22 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(16 * mm, height - 11 * mm, "XP Investimentos")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(16 * mm, height - 16.5 * mm, f"Carta mensal · {client['reference_month'].capitalize()}")
        canvas.drawRightString(width - 16 * mm, height - 11 * mm, client["name"])
        canvas.drawRightString(width - 16 * mm, height - 16.5 * mm,
                               f"Conta {client['account']} · Perfil {client['profile_pt']} · {client['letter_date']}")
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawString(16 * mm, 9 * mm, f"Assessor: {client['advisor_name']} ({client['advisor_code']})")
        canvas.drawRightString(width - 16 * mm, 9 * mm, f"Página {doc.page} de {MAX_PAGES}")
        canvas.restoreState()
    return draw


def build_story(letter_doc: dict, report: dict, layout: Layout, width: float) -> list:
    st = _styles(layout)
    letter, client = letter_doc["letter"], letter_doc["client"]
    body = lambda text: Paragraph(_esc(text), st["body"])  # noqa: E731

    charts = [c for c in letter.get("charts", []) if c in CHARTS][:2] or ["benchmarks", "contribution"]
    if len(charts) == 1:
        charts.append(next(c for c in ("benchmarks", "contribution", "allocation") if c != charts[0]))
    gap = 6 * mm
    chart_w = (width - gap) / 2
    chart_row = Table([[CHARTS[c](report, chart_w, layout.chart_height) for c in charts]],
                      colWidths=[chart_w + gap / 2, chart_w + gap / 2])
    chart_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    story = [_tiles(report, st, width), Spacer(1, 7 * mm),
             body(letter.get("greeting_pt", f"Prezado(a) {client['first_name']},")),
             body(letter.get("opening_pt", "")),
             Paragraph("Desempenho da carteira", st["h2"])]
    story += [body(p) for p in letter.get("performance_pt", [])]
    story += [Spacer(1, 2 * mm), chart_row, Spacer(1, 4 * mm), Paragraph("Destaques do mês", st["h2"]),
              _highlights(letter_doc, st, width), Spacer(1, 2 * mm),
              Paragraph("Cenário econômico", st["h2"]), body(letter.get("macro_pt", "")),
              Paragraph("Sugestões para conversarmos", st["h2"]), body(letter.get("suggestions_intro_pt", ""))]
    story += _suggestion_cards(letter, st, width)
    story += [Paragraph("O que esperar", st["h2"]), body(letter.get("outlook_pt", "")),
              body(letter.get("closing_pt", "")),
              Paragraph(f"Atenciosamente,<br/><b>{_esc(client['advisor_name'])}</b><br/>"
                        f"Assessor de Investimentos · XP Investimentos", st["body"]),
              Spacer(1, 3 * mm), Paragraph("Resultado por ativo no mês", st["h2"]),
              _results_table(report, st, width), Spacer(1, 3 * mm), Paragraph(DISCLAIMER, st["small"])]
    return story


def render(letter_doc: dict, report: dict, out: Path, layout: Layout = COMFORTABLE) -> int:
    """Write the PDF and return its number of pages."""
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=30 * mm, bottomMargin=16 * mm,
                            title=f"Carta mensal - {letter_doc['client']['name']}", author="XP Investimentos")
    page = _header_footer(letter_doc["client"])
    doc.build(build_story(letter_doc, report, layout, doc.width), onFirstPage=page, onLaterPages=page)
    return len(PdfReader(str(out)).pages)


def protect(path: Path, password: str) -> None:
    """Encrypt the PDF (AES-256) so it opens only with the client's password."""
    writer = PdfWriter(clone_from=str(path))
    writer.encrypt(user_password=password, owner_password=None, algorithm="AES-256")
    with path.open("wb") as handle:
        writer.write(handle)


def build_pdf(month_dir: Path, password: str | None = None) -> tuple[Path, int]:
    letter_doc = json.loads((month_dir / "letter.json").read_text(encoding="utf-8"))
    report = json.loads((month_dir / "profitability_market.json").read_text(encoding="utf-8"))
    out = month_dir / "letter.pdf"
    pages = render(letter_doc, report, out)
    if pages > MAX_PAGES:
        pages = render(letter_doc, report, out, COMPACT)
    if password:
        protect(out, password)
    return out, pages


def main() -> None:
    parser = argparse.ArgumentParser(description="Lay out a client's letter as PDF")
    parser.add_argument("month_dir", type=Path)
    parser.add_argument("--password", help="e.g. the first 6 digits of the client's CPF")
    args = parser.parse_args()
    out, pages = build_pdf(args.month_dir, args.password)
    status = "ok" if pages <= MAX_PAGES else f"too long: ask the agent for a shorter letter"
    print(f"{out}: {pages} page(s), {status}")


if __name__ == "__main__":
    main()

"""Lay out the approved letter as a two-page A4 PDF with charts.

Input: ``letter.json`` (text written by the Rivet agent) and ``profitability_market.json``
(figures computed by ``core.profitability``). The text is placed as written; every figure in
the charts, tiles and table comes from the profitability report, never from the LLM.

Layout
- Header, key figures, greeting, performance, the main chart (the consolidated portfolio over the last
  12 months, or since the first investment, against its benchmarks; without that history, the month
  against its benchmarks and where the result came from by class) and the highlights; then the XP scenario and how the
  portfolio sits in it for the client's profile, points to discuss, outlook, closing, the per-asset
  results table and the disclaimer, flowing over the two pages.
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
import matplotlib.ticker  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from core.briefing import CLASS_LABELS_PT, brl, class_contribution, pct, pp  # noqa: E402

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
    "de ativos. A avaliação e os pontos de atenção são para conversa com o seu assessor e devem ser considerados de "
    "acordo com o seu perfil de investidor. Rentabilidade passada não é garantia de rentabilidade futura. "
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
TIGHT = Layout(body=8.6, leading=11.2, chart_height=54 * mm, table_body=6.8)   # last resort before "too long"


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


def chart_attribution(report: dict, width: float, height: float) -> Image:
    """Where the month's result came from: contribution of each asset class, in p.p. of the portfolio return."""
    rows = [r for r in class_contribution(report) if abs(r["contribution_brl"]) >= 0.5][::-1]
    labels, values = [r["class"] for r in rows], [r["contribution_pp"] for r in rows]
    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    ax.barh(labels, values, color=[GAIN if v >= 0 else LOSS for v in values], height=0.6)
    span = max([abs(v) for v in values] + [0.01])
    for i, (r, v) in enumerate(zip(rows, values)):
        ax.text(v + (span * 0.03 if v >= 0 else -span * 0.03), i,
                f"{'+' if v >= 0 else ''}{_br(v, 2)} p.p. · {brl(r['contribution_brl']).replace('R$ ', 'R$')}",
                va="center", ha="left" if v >= 0 else "right", fontsize=6.5)
    low, high = min(values + [0]), max(values + [0])
    ax.set_xlim(low - span * 0.9 if low < 0 else 0, high + span * 0.9)
    ax.axvline(0, color=CHART_GREY, linewidth=0.8)
    ax.set_title(f"De onde veio o resultado ({pct(report['return_pct'])})", fontsize=8.5, loc="left",
                 fontweight="bold")
    _style_axes(ax)
    ax.set_xticks([])
    return _figure_to_image(fig, width, height)


MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def window_label(history: dict) -> str:
    return "desde a primeira aplicação" if history["since_first_investment"] else f"últimos {history['months']} meses"


def chart_history(history: dict, width: float, height: float) -> Image:
    """Consolidated portfolio over the window (cumulative %) against CDI, Ibovespa, inflation and the profile benchmark."""
    from datetime import date

    days = [date.fromisoformat(p["date"]) for p in history["points"]]
    lines = [("Benchmark do perfil", "PROFILE", CHART_INK, (0, (4, 2)), 1.2), ("CDI", "CDI", "#8C8C8C", "-", 1.2),
             ("Ibovespa", "IBOV", "#C9C9C9", "-", 1.2), ("Inflação (IPCA-15)", "IPCA", "#8C8C8C", ":", 1.2),
             ("Sua carteira", "portfolio", CHART_YELLOW, "-", 2.6)]
    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    x = list(range(len(days)))
    ends = []
    for label, key, color, style, lw in lines:
        values = [p[key] for p in history["points"]]
        ax.plot(x, values, color=color, linestyle=style, linewidth=lw, label=label, zorder=3 if key == "portfolio" else 2)
        ends.append((values[-1], label, color))
    # End labels, nudged apart so they never overlap.
    span = max(abs(v) for v, _, _ in ends) or 1
    placed: list[float] = []
    for value, label, color in sorted(ends):
        y = value
        while any(abs(y - other) < span * 0.075 for other in placed):
            y += span * 0.075
        placed.append(y)
        ax.text(x[-1] + 0.25, y, f"{'+' if value >= 0 else ''}{_br(value, 2)}%  {label}", va="center", fontsize=6.8,
                color=INK.hexval().replace("0x", "#") if color == CHART_YELLOW else color,
                fontweight="bold" if color == CHART_YELLOW else "normal")
    ax.axhline(0, color=CHART_GREY, linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{MONTHS_SHORT[d.month - 1]}/{d:%y}" for d in days], fontsize=6.5)
    ax.set_xlim(0, x[-1] + 3.2)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{_br(v, 0)}%"))
    ax.tick_params(axis="y", labelsize=6.5, length=0)
    ax.grid(axis="y", color="#EDEDED", linewidth=0.6)
    ax.set_title(f"Sua carteira x referências · {window_label(history)} (rentabilidade acumulada)", fontsize=8.5, loc="left",
                 fontweight="bold")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE.hexval().replace("0x", "#"))
    return _figure_to_image(fig, width, height)


CHARTS = {"benchmarks": chart_benchmarks, "attribution": chart_attribution}
LETTER_CHARTS = ["benchmarks", "attribution"]   # the consolidated result in context, then its sources


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


def _tile_row(caption: str, tiles: list[tuple], st: dict, width: float, accent: bool) -> Table:
    """One labelled row of figures: the caption says which period every tile below it measures.
    A tile is (label, value) or (label, value, note, colour) for a comparison."""
    note_style = ParagraphStyle("tn", parent=st["tile_label"], fontSize=6.6, leading=8)
    cells = []
    for label, value, *extra in tiles:
        note, colour = extra if extra else ("", None)
        shown = f'<font color="{colour}">{value}</font>' if colour else value
        cells.append([Paragraph(label, st["tile_label"]), Paragraph(shown, st["tile_value"])]
                     + ([Paragraph(note, note_style)] if note else []))
    table = Table([[Paragraph(caption, st["tag"])] + [""] * (len(tiles) - 1), cells],
                  colWidths=[width / len(tiles)] * len(tiles))
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("BOTTOMPADDING", (0, 0), (-1, 0), 2), ("LEFTPADDING", (0, 0), (-1, 0), 0),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT), ("LINEBEFORE", (1, 1), (-1, 1), 2, colors.white),
        ("LINEABOVE", (0, 1), (0, 1), 2.2, YELLOW if accent else GREY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 1), (-1, 1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
        ("LEFTPADDING", (0, 1), (-1, 1), 8),
    ]))
    return table


def _versus(label: str, short: str, portfolio: float, benchmark: float, period: str) -> tuple:
    """The portfolio against a benchmark as a difference in p.p., with the benchmark itself as a note.
    "CDI +11,45%" next to the portfolio read as "CDI + 11%"; the difference says who won."""
    diff = portfolio - benchmark
    return (f"Contra o {label}", pp(diff), f"{short} {period}: {pct(benchmark, signed=False)}", GAIN if diff >= 0 else LOSS)


def _tiles(report: dict, client: dict, st: dict, width: float, history: dict | None = None) -> list:
    """The month and the consolidated window in two labelled rows with the same four figures, so the client
    reads one against the other and no figure is taken for the other period."""
    bench, ret = report["benchmarks_pct"], report["return_pct"]
    rows = [_tile_row(f"NO MÊS · {client['reference_month'].upper()}",
                      [("Sua carteira", pct(ret)), ("Resultado em reais", brl(report["gain_brl"])),
                       _versus("CDI", "CDI", ret, bench["CDI"], "no mês"),
                       _versus("benchmark do perfil", "Benchmark", ret, bench["PROFILE"], "no mês")], st, width, True)]
    if history and history.get("months", 0) >= 2:
        total = history["total"]
        rows += [Spacer(1, 2 * mm), _tile_row(
            f"ACUMULADO · {window_label(history).upper()}",
            [("Sua carteira", pct(total["portfolio"])),
             ("Resultado em reais", brl(total["gain_brl"])) if "gain_brl" in total else ("Ibovespa", pct(total["IBOV"])),
             _versus("CDI", "CDI", total["portfolio"], total["CDI"], "no período"),
             _versus("benchmark do perfil", "Benchmark", total["portfolio"], total["PROFILE"], "no período")], st, width, False)]
    return rows


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


VIEW_PT = {"favorable": ("Favorável", GAIN), "neutral": ("Neutra", "#6B6B6B"), "unfavorable": ("Desfavorável", LOSS)}


def _class_views(letter_doc: dict, st: dict, width: float) -> Table | None:
    """The portfolio by class against the XP view: weights come from the portfolio facts, the view and the reading
    for the profile from the agent's assessment (rows for classes the client does not hold are dropped)."""
    weights = next((f["values"] for f in letter_doc["briefing"]["facts"]["facts"] if f["id"] == "class_weights"), {})
    rows = [[Paragraph(f"<b>{h}</b>", st["cell"]) for h in ("Classe", "Peso", "Visão da XP", "Para o seu perfil")]]
    for v in letter_doc["letter"].get("class_views", []):
        if v.get("asset_class") not in weights:
            continue
        label, color = VIEW_PT.get(v.get("xp_view"), ("—", "#333333"))
        rows.append([Paragraph(_esc(v["asset_class"]), st["cell"]), Paragraph(weights[v["asset_class"]], st["cell"]),
                     Paragraph(f'<font color="{color}"><b>{label}</b></font>', st["cell"]),
                     Paragraph(_esc(v.get("profile_fit_pt", "")), st["cell"])])
    if len(rows) == 1:
        return None
    table = Table(rows, colWidths=[width * 0.22, width * 0.1, width * 0.14, width * 0.54], repeatRows=1)
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _attention_cards(letter: dict, st: dict, width: float) -> list:
    flow = []
    for s in letter.get("attention_points", []):
        content = [Paragraph("PONTO DE ATENÇÃO", st["tag"]),
                   Paragraph(_esc(s.get("title_pt", "")), st["card_title"]),
                   Paragraph(_esc(s.get("text_pt", "")), ParagraphStyle("c", parent=st["body"], spaceAfter=0))]
        card = Table([[content]], colWidths=[width])
        card.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, 0), 2.5, YELLOW), ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
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


def build_story(letter_doc: dict, report: dict, layout: Layout, width: float, history: dict | None = None) -> list:
    st = _styles(layout)
    letter, client = letter_doc["letter"], letter_doc["client"]
    body = lambda text: Paragraph(_esc(text), st["body"])  # noqa: E731

    charts = LETTER_CHARTS
    gap = 6 * mm
    chart_w = (width - gap) / 2
    chart_row = Table([[CHARTS[c](report, chart_w, layout.chart_height) for c in charts]],
                      colWidths=[chart_w + gap / 2, chart_w + gap / 2])
    chart_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    consolidated = bool(history and history.get("months", 0) >= 2)
    story = [*_tiles(report, client, st, width, history if consolidated else None), Spacer(1, 4 * mm),
             body(letter.get("greeting_pt", f"Prezado(a) {client['first_name']},")),
             body(letter.get("opening_pt", "")),
             Paragraph(f"Desempenho no mês · {client['reference_month']}", st["h2"])]
    story += [body(p) for p in letter.get("performance_pt", [])]
    if consolidated:
        # The consolidated view is the main chart; the month's detail by asset is in the table at the end.
        story += [Paragraph(f"Desempenho acumulado · {window_label(history)}", st["h2"]),
                  body(letter.get("consolidated_pt", ""))]
        main_chart = [chart_history(history, width, layout.chart_height * 1.12)]
        since = history.get("since_purchase")
        if since:
            start = since.get("first_investment")
            start = f", desde {start[8:10]}/{start[5:7]}/{start[:4]}" if start else ""
            main_chart.append(Paragraph(
                f"<b>Desde a aplicação{start}</b> (preço médio das ações e valor aplicado nos fundos e títulos, contra o valor "
                f"atual; não inclui o saldo em conta): {brl(since['cost'])} aplicados, hoje {brl(since['value'])}, "
                f"resultado de <b>{brl(since['gain_brl'])} ({pct(since['return_pct'])})</b>.", st["cell"]))
        main_chart.append(Paragraph(_esc(history["note"]), st["small"]))
    else:
        main_chart = [chart_row]
    story += [Spacer(1, 2 * mm), *main_chart, Spacer(1, 4 * mm), Paragraph("Destaques do mês", st["h2"]),
              _highlights(letter_doc, st, width), Spacer(1, 2 * mm),
              Paragraph("Cenário econômico e sua carteira", st["h2"]), body(letter.get("macro_pt", ""))]
    views = _class_views(letter_doc, st, width)
    if views:
        story += [views, Spacer(1, 3 * mm)]
    story += [body(letter.get("assessment_pt", ""))]
    if letter.get("attention_points"):
        story += [Paragraph("Pontos para conversarmos", st["h2"])]
    story += _attention_cards(letter, st, width)
    # Fixed order: the per-asset table, then the outlook, the closing and the signature, then the disclaimer.
    story += [Paragraph("Resultado por ativo no mês", st["h2"]), _results_table(report, st, width),
              Paragraph("O que esperar", st["h2"]), body(letter.get("outlook_pt", "")),
              body(letter.get("closing_pt", "")),
              Paragraph(f"Atenciosamente,<br/><b>{_esc(client['advisor_name'])}</b><br/>"
                        f"Assessor de Investimentos · XP Investimentos", st["body"]),
              Spacer(1, 3 * mm), Paragraph(DISCLAIMER, st["small"])]
    return story


def render(letter_doc: dict, report: dict, out: Path, layout: Layout = COMFORTABLE, history: dict | None = None) -> int:
    """Write the PDF and return its number of pages."""
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=30 * mm, bottomMargin=16 * mm,
                            title=f"Carta mensal - {letter_doc['client']['name']}", author="XP Investimentos")
    page = _header_footer(letter_doc["client"])
    doc.build(build_story(letter_doc, report, layout, doc.width, history), onFirstPage=page, onLaterPages=page)
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
    history_path = month_dir / "history.json"
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else None
    out = month_dir / "letter.pdf"
    pages = render(letter_doc, report, out, history=history)
    for layout in (COMPACT, TIGHT):
        if pages <= MAX_PAGES:
            break
        pages = render(letter_doc, report, out, layout, history)
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

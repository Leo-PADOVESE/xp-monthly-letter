"""Run the Rivet agent for one client and keep only a letter that passes the checks.

Flow (Rivet decides, Python executes):
1. Macro digest: graph ``macro_digest`` runs once per month and is cached for every client.
2. Briefing: statement, profile, formatted results, 12-month window, portfolio facts and the macro
   digest (``core.briefing``), written to ``briefing.json``.
3. Graph ``monthly_letter``, with ``briefing.json`` (every figure already calculated) as its only data
   input: the Analyst (profile, performance and an assessment of the portfolio against the client's
   profile and the XP scenario, no buy/sell orders), the Writer and the Reviewer.
4. Checks, deterministic: every figure in the letter must exist in the briefing; the month and the 12-month
   window are not mixed; the portfolio is compared with the CDI and the profile benchmark in p.p.; a matured
   bond is not quoted as a result; no promise of returns; every attention point cites a portfolio fact; the
   outlook names the client's own classes; the length fits. Plus the critic's high-severity findings on facts,
   time frames, coherence, names and structure. If any fails, the letter is rewritten (up to twice) with the
   issues as revision notes; if it still fails it is saved as ``needs_review`` for the advisor.

CLI:
    python -m core.letter_ai data/clients/albert_da_silva/2025-05
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from core import periods
from core.briefing import client_card, formatted_history, formatted_results, portfolio_facts
from core.ingestion import load_portfolio, parse_risk_profile_label, pdf_to_text, portfolio_to_text
from core.profitability import load_settings

ROOT = Path(__file__).resolve().parents[1]
RIVET_RUNNER = ROOT / "rivet" / "run_graph.mjs"
# Wording that implies a promise of returns; the critic judges nuance, this catches the obvious cases.
PROMISE = re.compile(
    r"(?:retorno|rentabilidade|ganho|lucro)s?\s+(?:garantid|cert)\w*|sem risco|garanti\w*\s+(?:o |a |os |as )?(?:retorno|rentabilidade|ganho|lucro)"
    r"|(?:melhor|aument|elev|potencializ|maximiz|turbin)\w*\s+(?:a |o |os |as |sua |seu |seus |suas )?"
    r"(?:rentabilidade|retornos?|ganhos?|rendimentos?|resultados?)\b",
    re.IGNORECASE)
NUMBER = re.compile(r"R\$\s?-?[\d.]+,\d{2}|[+-]?\d+(?:,\d+)?\s?%|[+-]?\d+(?:,\d+)?\s?p\.p\.")


BLOCKING_RULES = ("fatos", "período", "coerência", "nomes")


def _plain(text: str) -> str:
    """Lower case, single spaces and straight quotes, to find a quoted passage in the letter."""
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").strip(' ."\'…')
    return re.sub(r"\s+", " ", text).lower()


def _quoted(quote: str, text: str) -> bool:
    """The quote, or its first part before an ellipsis, appears in the letter."""
    head = _plain(re.split(r"…|\.\.\.", quote)[0])
    return len(head) >= 12 and head[:80] in text


class LetterError(RuntimeError):
    pass


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value lines), without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def run_graph(graph: str, inputs: dict[str, str]) -> tuple[dict[str, str], dict]:
    """Run one Rivet graph through rivet/run_graph.mjs; returns (outputs, token usage)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(inputs, handle, ensure_ascii=False)
    try:
        done = subprocess.run(["node", str(RIVET_RUNNER), graph, handle.name], capture_output=True,
                              text=True, encoding="utf-8", cwd=ROOT, timeout=600)
    finally:
        os.unlink(handle.name)
    if done.returncode != 0:
        raise LetterError(f"Rivet graph {graph} failed:\n{done.stderr.strip()}")
    result = json.loads(done.stdout)
    return result["outputs"], result["usage"]


def parse_json(raw: str | None, step: str) -> dict:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LetterError(f"Step {step} did not return valid JSON: {exc}\n{text[:500]}") from exc


# ----------------------------------------------------------------- macro digest

def macro_report(period: periods.Period) -> Path:
    if not period.macro_report.exists():
        raise LetterError(f"Macro research de {period.reference:%m/%Y} não encontrado: anexe na tela Macro")
    return period.macro_report


def macro_digest(macro_pdf: Path, letter_date: date, model: str) -> dict:
    """Digest the month's XP macro report once and cache it for every client."""
    text = pdf_to_text(macro_pdf)
    key = hashlib.sha256(f"{text}|{letter_date}|{model}".encode()).hexdigest()[:12]
    cache = ROOT / "data" / "cache" / f"macro_digest_{letter_date:%Y-%m}_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    outputs, usage = run_graph("macro_digest", {"macro_text": text, "letter_date": letter_date.isoformat(),
                                                "model": model})
    digest = parse_json(outputs["macro_digest"], "macro_digest")
    digest["_usage"] = usage
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest


# ---------------------------------------------------------------------- checks

GREETING = re.compile(r"^(?:Car[oa]|Prezad[oa])\s+[^\s,]+,\s*")
# The PDF signs the letter; a sign-off inside the text ("Atenciosamente, Antonio Bicudo.") would sign it twice.
SIGN_OFF = re.compile(r"\s*(?:Atenciosamente|Cordialmente|Abraços|Um abraço)\b.*$", re.IGNORECASE | re.DOTALL)


def _client_voice(text: str, client_name: str) -> str:
    for name in dict.fromkeys(n for n in (client_name, client_name.split()[0] if client_name else "") if n):
        text = re.sub(rf"\b([Aa]) (carteira|portfólio) de {re.escape(name)}\b",
                      lambda m: ("S" if m.group(1) == "A" else "s") + ("ua carteira" if m.group(2) == "carteira"
                                                                      else "eu portfólio"), text)
        text = re.sub(rf"\b([Oo]) portfólio de {re.escape(name)}\b",
                      lambda m: ("S" if m.group(1) == "O" else "s") + "eu portfólio", text)
    # Internal jargon: the agent reads a "digest"; the client reads the XP macro report.
    text = re.sub(r"\b(n?o) (?:digest|resumo) macro(?:econômico)?(?: da XP)?",
                  lambda m: f"{m.group(1)} relatório macro da XP", text)
    return re.sub(r"\bdigest\b", "relatório", text)


def tidy(letter: dict, client_name: str = "") -> dict:
    """Deterministic polish: the greeting belongs only in greeting_pt (drafts repeated "Caro Bruno,"), the letter
    speaks to the client ("a carteira de Carla Mendes" -> "sua carteira") and no internal jargon reaches it."""
    paragraphs = [GREETING.sub("", p) for p in letter.get("performance_pt", [])]
    letter["performance_pt"] = [_client_voice(p[:1].upper() + p[1:], client_name) for p in paragraphs if p]
    for key in ("opening_pt", "consolidated_pt", "macro_pt", "assessment_pt", "outlook_pt", "closing_pt"):
        letter[key] = _client_voice(letter.get(key, ""), client_name)
    for key in ("outlook_pt", "closing_pt"):
        letter[key] = SIGN_OFF.sub("", letter[key])
    for s in letter.get("attention_points", []):
        s["text_pt"] = _client_voice(s.get("text_pt", ""), client_name)
    return letter


def letter_text(letter: dict) -> str:
    parts = [letter.get(k, "") for k in ("subject_pt", "greeting_pt", "opening_pt", "macro_pt",
                                          "assessment_pt", "outlook_pt", "closing_pt")]
    parts += letter.get("performance_pt", [])
    parts.append(letter.get("consolidated_pt", ""))
    parts += [f"{s.get('title_pt', '')}. {s.get('text_pt', '')}" for s in letter.get("attention_points", [])]
    parts += [v.get("profile_fit_pt", "") for v in letter.get("class_views", [])]
    return "\n".join(p for p in parts if p)


def _norm(figure: str) -> tuple[str, float]:
    """("%", 15.0) for "15%", "15,00%" or "+15,0%": the same value however it is written."""
    kind = "R$" if "R$" in figure else "p.p." if "p.p." in figure else "%"
    digits = re.sub(r"[^\d,]", "", figure.replace(".", "") if kind == "R$" else figure.replace("p.p.", ""))
    return kind, round(float(digits.replace(",", ".")), 2)


def check_numbers(letter: dict, *sources: object) -> list[str]:
    """Figures in the letter that do not appear in any source (results, facts, macro digest).

    Figures are compared by value, ignoring sign and number of decimals, so "15%" matches
    "15,00%"; the sign and wording are the critic's job."""
    allowed = {_norm(m) for s in sources for m in NUMBER.findall(json.dumps(s, ensure_ascii=False))}
    found = NUMBER.findall(letter_text(letter))
    return sorted({f for f in found if _norm(f) not in allowed})


def check_scope(letter: dict, results: dict) -> list[str]:
    """Figures quoted in the wrong period: a 12-month figure in the month's paragraphs, or a month figure in the
    consolidated paragraph. The PDF lays them out under "No mês" and "Últimos 12 meses", so a mix misleads."""
    window = results.get("consolidated_window")
    if not window:
        return []
    values = lambda data: {_norm(m) for m in NUMBER.findall(json.dumps(data, ensure_ascii=False))}  # noqa: E731
    window_only = values({k: v for k, v in window.items() if k != "how_it_was_built"}) - values(results["formatted"])
    month_only = values(results["formatted"]) - values(window)
    month_text = " ".join(letter.get("performance_pt", []))
    problems = [f"{f} é do acumulado de 12 meses, mas está no parágrafo do mês"
                for f in NUMBER.findall(month_text) if _norm(f) in window_only]
    problems += [f"{f} é do mês, mas está no parágrafo do acumulado"
                 for f in NUMBER.findall(letter.get("consolidated_pt", "")) if _norm(f) in month_only]
    return sorted(set(problems))


def check_matured_as_result(letter: dict, facts: dict) -> list[str]:
    """A matured bond quoted in the month's performance: its 0,00% is a payout already received, not a result,
    and it is left out of the best and worst performers ("menor retorno" once named the matured CDB)."""
    matured = [f["id"].split(":", 1)[1] for f in facts["facts"] if f["id"].startswith("matured:")]
    text = " ".join(letter.get("performance_pt", []))
    return [name for name in matured if name in text]


GENERIC_TERMS = {"Ações": "ações", "Renda fixa (CDB)": "cdb", "Saldo em conta": "saldo", "Fundos de renda fixa": "renda fixa",
                 "Fundos multimercado": "multimercado", "Fundos de ações": "fundos de ações"}


def check_specific_ending(letter: dict, facts: dict) -> list[str]:
    """The outlook must name something this client holds; generic endings ("a diversificação pode mitigar riscos")
    fit any client and read as a template."""
    weights = next((f["values"] for f in facts["facts"] if f["id"] == "class_weights"), {})
    terms = [GENERIC_TERMS.get(c, c.lower()) for c in weights] + ["renda fixa", "fundo", "bolsa"]
    outlook = letter.get("outlook_pt", "").lower()
    return [] if any(t in outlook for t in terms) else ["'O que esperar' não cita nenhuma classe ou ativo da carteira"]


def check_versus_benchmarks(letter: dict, results: dict) -> list[str]:
    """The portfolio is always read against its benchmarks as a difference in p.p. ("+2,90 p.p. acima do CDI"),
    in the month and in the window: quoted side by side, "CDI +11,45%" read as the portfolio earning CDI + 11%."""
    def missing(text: str, figures: dict, where: str) -> list[str]:
        found = {_norm(f) for f in NUMBER.findall(text)}
        return [f"{where}: falta a diferença contra o {name} ({figures[key]})"
                for key, name in (("excess_vs_cdi", "CDI"), ("excess_vs_profile_benchmark", "benchmark do perfil"))
                if key in figures and _norm(figures[key]) not in found]
    problems = missing(" ".join(letter.get("performance_pt", [])), results["formatted"], "desempenho do mês")
    if results.get("consolidated_window"):
        problems += missing(letter.get("consolidated_pt", ""), results["consolidated_window"], "acumulado")
    return problems


def check_promises(letter: dict) -> list[str]:
    """Passages that read as a promise of returns, e.g. "pode melhorar a rentabilidade"."""
    return sorted({m.group(0) for m in PROMISE.finditer(letter_text(letter))})


def check_attention_points(letter: dict, facts: dict) -> list[str]:
    """Problems with the attention points: not anchored in a portfolio fact, repeated, or more than three."""
    known = {f["id"] for f in facts["facts"]}
    ids = [s.get("fact_id") for s in letter.get("attention_points", [])]
    problems = [f"ponto de atenção sem fato da carteira: {i}" for i in ids if i not in known]
    problems += [f"fato repetido: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if len(ids) > 3:
        problems.append(f"{len(ids)} pontos de atenção (o máximo é 3)")
    return problems


def word_count(letter: dict) -> int:
    return len(letter_text(letter).split())


# ---------------------------------------------------------------------- letter

def generate(month_dir: Path, max_rewrites: int = 2) -> dict:
    load_env()
    settings = load_settings()
    llm = settings.get("llm", {})
    model = llm.get("model", "gpt-4o-mini")
    writer_model = llm.get("writer_model", model)
    period = periods.from_folder(month_dir.name)
    letter_date, period_end = period.letter_date, period.end

    portfolio = load_portfolio(month_dir)
    risk_text = pdf_to_text(month_dir.parent / "risk_profile.pdf")
    profile = parse_risk_profile_label(risk_text)
    report_path = month_dir / "profitability_market.json"
    if not report_path.exists():
        raise LetterError(f"{report_path} not found: run python -m core.profitability {month_dir} first")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    digest = macro_digest(macro_report(period), letter_date, model)
    results = formatted_results(report)
    history_path = month_dir / "history.json"
    if history_path.exists():
        results["consolidated_window"] = formatted_history(json.loads(history_path.read_text(encoding="utf-8")))
    weights = settings["benchmarks"][profile]
    results["formatted"]["profile_benchmark_composition"] = " + ".join(
        f"{w * 100:.0f}% {'Ibovespa' if k == 'IBOV' else k}" for k, w in weights.items())
    facts = portfolio_facts(portfolio, report, profile)
    client = client_card(portfolio, profile, letter_date, period_end)
    # Data-quality warnings (stale quota dates, cent differences) are for the advisor, not the client.
    portfolio_text = portfolio_to_text(portfolio).split("\nData warnings:")[0].rstrip()
    digest_for_llm = {k: v for k, v in digest.items() if not k.startswith("_")}

    # Everything the agent needs, already calculated, in one file: the Rivet graph's only data input.
    briefing = {
        "client": client,
        "profile": {"label": profile, "document_text": risk_text},
        # The statement's "rentabilidade" columns run since each investment; the month's figures are in "results".
        "statement_note": "No extrato, a rentabilidade de cada ativo é acumulada desde a aplicação; o retorno do mês "
                          "de cada ativo está em results.positions.",
        "statement": portfolio_text,
        "results": results,
        "portfolio_facts": facts,
        "macro_digest": digest_for_llm,
    }
    (month_dir / "briefing.json").write_text(json.dumps(briefing, ensure_ascii=False, indent=1), encoding="utf-8")
    inputs = {"briefing": json.dumps(briefing, ensure_ascii=False), "revision_notes": "", "model": model,
              "writer_model": writer_model}

    attempts = []
    for attempt in range(max_rewrites + 1):
        outputs, usage = run_graph("monthly_letter", inputs)
        steps = {name: parse_json(raw, name) for name, raw in outputs.items()}
        letter, critic = tidy(steps["letter"], client["name"]), steps["critic"]
        # The class table comes from the Analyst's assessment; weights are laid out from the facts by the PDF.
        letter["class_views"] = steps["analysis"].get("assessment", {}).get("class_views", [])
        unknown = check_numbers(letter, results, facts, digest_for_llm)
        words = word_count(letter)
        # Figures are verified by check_numbers; the critic judges meaning and tone.
        notes = critic.get("issues", [])
        # The critic's high findings force a rewrite only on meaning (facts, time frames, coherence, names) and only
        # when the passage it quotes is really in the letter: in tests it contradicted itself ("+0,41 p.p., não
        # +0,41 p.p.") and blocked every letter. Structure and style stay as notes for the advisor; the outlook is
        # checked in code.
        text = _plain(letter_text(letter))
        flagged = [{**n, "rule": n.get("rule", "fatos")} for n in notes
                   if n.get("severity") == "high" and n.get("rule") in BLOCKING_RULES and _quoted(n.get("quote", ""), text)]
        issues: list[dict] = list(flagged)
        if unknown:
            issues.append({"severity": "high", "rule": "números",
                           "problem": f"Valores que não existem nos dados: {', '.join(unknown)}",
                           "fix": "Use apenas os valores exatamente como aparecem nos dados fornecidos."})
        wrong_points = check_attention_points(letter, facts)
        if wrong_points:
            issues.append({"severity": "high", "rule": "pontos de atenção", "problem": "; ".join(wrong_points),
                           "fix": "Use de 1 a 3 pontos, cada um com o fact_id de um fato da carteira."})
        generic = check_specific_ending(letter, facts)
        if generic:
            issues.append({"severity": "high", "rule": "estrutura", "problem": "; ".join(generic),
                           "fix": "Em 'O que esperar', diga o que acompanhar nas classes que o cliente tem, pelo cenário "
                                  "da XP; no desfecho, convide para conversar sobre os pontos de atenção da carta."})
        quoted_matured = check_matured_as_result(letter, facts)
        if quoted_matured:
            issues.append({"severity": "high", "rule": "fatos",
                           "problem": f"Título vencido citado no desempenho do mês: {', '.join(quoted_matured)}",
                           "fix": "Não cite o título vencido no desempenho; o pior desempenho é o de 'worst_performer'. "
                                  "O vencimento é um ponto de atenção (valor disponível para reinvestir)."})
        versus = check_versus_benchmarks(letter, results)
        if versus:
            issues.append({"severity": "high", "rule": "benchmark", "problem": "; ".join(versus),
                           "fix": "Compare a carteira com o CDI e com o benchmark do perfil pela diferença em p.p., "
                                  "dizendo se ficou acima ou abaixo (ex.: '3,84 p.p. abaixo do CDI, que rendeu 11,45%')."})
        mixed = check_scope(letter, results)
        if mixed:
            issues.append({"severity": "high", "rule": "período", "problem": "; ".join(mixed),
                           "fix": "Em performance_pt só números do mês; em consolidated_pt só os da janela de 12 meses."})
        promises = check_promises(letter)
        if promises:
            issues.append({"severity": "high", "rule": "promessa", "problem": f"Promessa de retorno: {', '.join(promises)}",
                           "fix": "Descreva o que a movimentação faz pela carteira (diversifica, reduz concentração, "
                                  "dá liquidez, alinha ao perfil), sem dizer que melhora ou aumenta o retorno."})
        if not 300 <= words <= 600:
            issues.append({"severity": "high", "rule": "tamanho", "problem": f"{words} palavras",
                           "fix": "Ajuste o texto para ficar entre 330 e 480 palavras."})
        # Code checks are the gate. After the last rewrite, findings left only by the critic go to the advisor as
        # notes (the advisor reviews every letter): in tests it kept flagging correct sentences ("ARZZ3 teve o melhor
        # desempenho" when LREN3 contributed more in reais) and held every letter.
        last = attempt == max_rewrites
        approved = not issues or (last and len(issues) == len(flagged))
        attempts.append({"attempt": attempt + 1, "usage": usage, "words": words, "unknown_numbers": unknown,
                         "critic": critic, "issues": issues, "advisor_notes": notes})
        if approved:
            break
        inputs["revision_notes"] = json.dumps(issues, ensure_ascii=False, indent=1)

    result = {
        "status": "approved" if approved else "needs_review",
        "client": client, "letter": letter, "steps": steps,
        "briefing": {"results": results, "facts": facts},
        "advisor_notes": attempts[-1]["advisor_notes"],
        "macro_digest": digest_for_llm, "attempts": attempts, "model": model, "writer_model": writer_model,
    }
    out = month_dir / "letter.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a client's monthly letter with the Rivet agent")
    parser.add_argument("month_dir", type=Path)
    args = parser.parse_args()
    result = generate(args.month_dir)
    cost = sum(a["usage"].get("cost", 0) for a in result["attempts"])
    last = result["attempts"][-1]
    print(f"{result['client']['name']}: {result['status']} after {len(result['attempts'])} draft(s), "
          f"{last['words']} words, US${cost:.4f} -> {args.month_dir / 'letter.json'}")
    for issue in last["issues"]:
        print(f"  ! [{issue['severity']}] {issue.get('rule', '')}: {issue['problem']}")


if __name__ == "__main__":
    main()

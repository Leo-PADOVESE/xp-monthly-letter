"""Run the Rivet agent for one client and keep only a letter that passes the checks.

Flow (Rivet decides, Python executes):
1. Macro digest: graph ``macro_digest`` runs once per month and is cached for every client.
2. Briefing: statement, profile, formatted results and portfolio facts (``core.briefing``).
3. Graph ``monthly_letter``: profile, performance analysis, the choice among the rule-based suggestion
   candidates (``core.suggestions``), letter and critic.
4. Checks: the critic's verdict plus a deterministic one, every figure in the letter must exist
   in the briefing. If either fails, the letter is rewritten once with the issues as revision
   notes; if it still fails it is saved as ``needs_review`` for the advisor.

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

from core.briefing import client_card, formatted_results, portfolio_facts
from core.ingestion import load_portfolio, parse_risk_profile_label, pdf_to_text, portfolio_to_text
from core.profitability import load_settings
from core.suggestions import candidates

ROOT = Path(__file__).resolve().parents[1]
RIVET_RUNNER = ROOT / "rivet" / "run_graph.mjs"
# Wording that implies a promise of returns; the critic judges nuance, this catches the obvious cases.
PROMISE = re.compile(
    r"(?:retorno|rentabilidade|ganho|lucro)s?\s+(?:garantid|cert)\w*|sem risco|garanti\w*\s+(?:o |a |os |as )?(?:retorno|rentabilidade|ganho|lucro)"
    r"|(?:melhor|aument|elev|potencializ|maximiz|turbin)\w*\s+(?:a |o |os |as |sua |seu |seus |suas )?"
    r"(?:rentabilidade|retornos?|ganhos?|rendimentos?|resultados?)\b",
    re.IGNORECASE)
NUMBER = re.compile(r"R\$\s?-?[\d.]+,\d{2}|[+-]?\d+(?:,\d+)?\s?%|[+-]?\d+(?:,\d+)?\s?p\.p\.")


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


def _client_voice(text: str, client_name: str) -> str:
    if client_name:
        text = re.sub(rf"\b([Aa]) (carteira|portfólio) de {re.escape(client_name)}",
                      lambda m: ("S" if m.group(1) == "A" else "s") + f"ua carteira" if m.group(2) == "carteira"
                      else ("S" if m.group(1) == "A" else "s") + "eu portfólio", text)
        text = re.sub(rf"\b([Oo]) portfólio de {re.escape(client_name)}",
                      lambda m: ("S" if m.group(1) == "O" else "s") + "eu portfólio", text)
    return re.sub(r"\b(no|o) digest macro", lambda m: f"{m.group(1)} relatório macro da XP", text)


def tidy(letter: dict, client_name: str = "") -> dict:
    """Deterministic polish: the greeting belongs only in greeting_pt (drafts repeated "Caro Bruno,"), the letter
    speaks to the client ("a carteira de Carla Mendes" -> "sua carteira") and no internal jargon reaches it."""
    paragraphs = [GREETING.sub("", p) for p in letter.get("performance_pt", [])]
    letter["performance_pt"] = [_client_voice(p[:1].upper() + p[1:], client_name) for p in paragraphs if p]
    for key in ("opening_pt", "macro_pt", "suggestions_intro_pt", "outlook_pt", "closing_pt"):
        letter[key] = _client_voice(letter.get(key, ""), client_name)
    for s in letter.get("suggestions", []):
        s["text_pt"] = _client_voice(s.get("text_pt", ""), client_name)
    return letter


def letter_text(letter: dict) -> str:
    parts = [letter.get(k, "") for k in ("subject_pt", "greeting_pt", "opening_pt", "macro_pt",
                                          "suggestions_intro_pt", "outlook_pt", "closing_pt")]
    parts += letter.get("performance_pt", [])
    parts += [f"{s.get('title_pt', '')}. {s.get('text_pt', '')}" for s in letter.get("suggestions", [])]
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


def check_promises(letter: dict) -> list[str]:
    """Passages that read as a promise of returns, e.g. "pode melhorar a rentabilidade"."""
    return sorted({m.group(0) for m in PROMISE.finditer(letter_text(letter))})


def check_suggestions(letter: dict, options: list[dict]) -> list[str]:
    """Problems with the chosen suggestions: unknown or repeated candidates, a changed type, too few or many."""
    by_id = {o["id"]: o for o in options}
    chosen = letter.get("suggestions", [])
    ids = [s.get("candidate_id") for s in chosen]
    problems = [f"sugestão fora das candidatas: {i}" for i in ids if i not in by_id]
    problems += [f"candidata repetida: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    problems += [f"tipo trocado em {s['candidate_id']}" for s in chosen
                 if s.get("candidate_id") in by_id and s.get("type") != by_id[s["candidate_id"]]["type"]]
    if not 2 <= len(chosen) <= 3 and len(options) >= 2:
        problems.append(f"{len(chosen)} sugestões (o esperado é 2 ou 3)")
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
    letter_date, period_end = settings["letter_date"], settings["period_end"]

    portfolio = load_portfolio(month_dir)
    risk_text = pdf_to_text(month_dir.parent / "risk_profile.pdf")
    profile = parse_risk_profile_label(risk_text)
    report_path = month_dir / "profitability_market.json"
    if not report_path.exists():
        raise LetterError(f"{report_path} not found: run python -m core.profitability {month_dir} first")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    digest = macro_digest(ROOT / settings["macro_report"], letter_date, model)
    results = formatted_results(report)
    weights = settings["benchmarks"][profile]
    results["formatted"]["profile_benchmark_composition"] = " + ".join(
        f"{w * 100:.0f}% {'Ibovespa' if k == 'IBOV' else k}" for k, w in weights.items())
    facts = portfolio_facts(portfolio, report, profile)
    client = client_card(portfolio, profile, letter_date, period_end)
    options = candidates(portfolio, report, facts, profile, weights)
    # Data-quality warnings (stale quota dates, cent differences) are for the advisor, not the client.
    portfolio_text = portfolio_to_text(portfolio).split("\nData warnings:")[0].rstrip()
    digest_for_llm = {k: v for k, v in digest.items() if not k.startswith("_")}

    inputs = {
        "client": json.dumps(client, ensure_ascii=False),
        "profile_label": profile,
        "risk_profile_text": risk_text,
        "portfolio_text": portfolio_text,
        "profitability": json.dumps(results, ensure_ascii=False, indent=1),
        "portfolio_facts": json.dumps(facts, ensure_ascii=False, indent=1),
        "suggestion_candidates": json.dumps(options, ensure_ascii=False, indent=1),
        "macro_digest": json.dumps(digest_for_llm, ensure_ascii=False, indent=1),
        "revision_notes": "",
        "model": model,
        "writer_model": writer_model,
    }

    attempts = []
    for attempt in range(max_rewrites + 1):
        outputs, usage = run_graph("monthly_letter", inputs)
        steps = {name: parse_json(raw, name) for name, raw in outputs.items()}
        letter, critic = tidy(steps["letter"], client["name"]), steps["critic"]
        unknown = check_numbers(letter, results, facts, digest_for_llm, options)
        words = word_count(letter)
        # Figures are verified by check_numbers; the critic judges suitability, tone and promises.
        # The reviewer is advisory: in tests it blocked correct sentences (e.g. "0,99% beat 1,06%"), so its
        # findings go to the advisor as notes; blocking checks are deterministic (figures, promises, suggestions).
        issues: list[dict] = []
        notes = critic.get("issues", [])
        if unknown:
            issues.append({"severity": "high", "rule": "números",
                           "problem": f"Valores que não existem nos dados: {', '.join(unknown)}",
                           "fix": "Use apenas os valores exatamente como aparecem nos dados fornecidos."})
        wrong_suggestions = check_suggestions(letter, options)
        if wrong_suggestions:
            issues.append({"severity": "high", "rule": "sugestões", "problem": "; ".join(wrong_suggestions),
                           "fix": "Escolha de 2 a 3 sugestões entre as candidatas, copiando candidate_id e type."})
        promises = check_promises(letter)
        if promises:
            issues.append({"severity": "high", "rule": "3", "problem": f"Promessa de retorno: {', '.join(promises)}",
                           "fix": "Descreva o que a movimentação faz pela carteira (diversifica, reduz concentração, "
                                  "dá liquidez, alinha ao perfil), sem dizer que melhora ou aumenta o retorno."})
        if not 300 <= words <= 600:
            issues.append({"severity": "high", "rule": "tamanho", "problem": f"{words} palavras",
                           "fix": "Ajuste o texto para ficar entre 380 e 520 palavras."})
        approved = not issues
        attempts.append({"attempt": attempt + 1, "usage": usage, "words": words, "unknown_numbers": unknown,
                         "critic": critic, "issues": issues, "advisor_notes": notes})
        if approved:
            break
        inputs["revision_notes"] = json.dumps(issues, ensure_ascii=False, indent=1)

    result = {
        "status": "approved" if approved else "needs_review",
        "client": client, "letter": letter, "steps": steps,
        "briefing": {"results": results, "facts": facts, "suggestion_candidates": options},
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

"""End-to-end runs for the platform: add a client, generate one letter or a batch in parallel.

Every step reuses the modules of the pipeline:
    statement PDF -> ingestion (code reader; Rivet fallback reader when the layout is unknown)
    -> profitability (Yahoo / CVM / BCB) -> letter (Rivet agent + checks) -> letter PDF.

A letter takes 1 to 2 minutes, almost all of it waiting for the LLM, so a batch runs many
clients at once in threads: 300 clients take about as long as ~15-20 sequential letters.
"""

from __future__ import annotations

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from core import crm, periods
from core.briefing import PROFILE_PT
from core.ingestion import (IngestionError, load_portfolio, parse_risk_profile_label, parse_xp_portfolio, pdf_to_text,
                            portfolio_from_extraction, portfolio_to_text)
from core.letter_ai import generate, load_env, macro_digest, macro_report, parse_json, run_graph
from core.letter_pdf import build_pdf
from core.profitability import load_settings
from core.profitability import run as run_profitability

BATCH_WORKERS = 8


def current_month() -> str:
    """Folder of the latest letters prepared (e.g. 2025-05, the letters of April 2025)."""
    folders = sorted({p.parent.name for p in crm.CLIENTS_DIR.glob("*/*/portfolio.pdf")})
    return folders[-1] if folders else periods.recent()[0].folder


def month_dir(slug: str, month: str | None = None) -> Path:
    return crm.CLIENTS_DIR / slug / (month or current_month())


# ---------------------------------------------------------------------- ingestion

def read_statement(pdf: Path) -> tuple[object, str]:
    """Hybrid reader: code first (exact), the Rivet extraction graph only when the layout is unknown.

    Returns (portfolio, reader). The fallback result goes through the same reconciliation checks."""
    text = pdf_to_text(pdf)
    try:
        return parse_xp_portfolio(text), "code"
    except IngestionError as code_error:
        load_env()
        model = load_settings().get("llm", {}).get("model", "gpt-4o-mini")
        try:
            outputs, _ = run_graph("portfolio_extraction", {"statement_text": text, "model": model})
            return portfolio_from_extraction(parse_json(outputs["portfolio_json"], "portfolio_extraction")), "rivet"
        except Exception as fallback_error:
            raise IngestionError(f"Extrato não reconhecido: {code_error}. Leitura por IA também falhou: "
                                 f"{fallback_error}") from fallback_error


def add_statement(slug: str, statement_pdf: bytes, month: str | None = None) -> dict:
    """The month's statement of a registered client: read it, check it and compute the profitability."""
    import tempfile

    row = crm.client(slug)
    if not (row and row["profile"]):
        raise IngestionError("Anexe o suitability do cliente antes do extrato: o perfil define o benchmark")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_pdf = Path(tmp) / "portfolio.pdf"
        tmp_pdf.write_bytes(statement_pdf)
        portfolio, reader = read_statement(tmp_pdf)
    if row["account"] and portfolio.account and str(portfolio.account) != str(row["account"]):
        raise IngestionError(f"O extrato é da conta {portfolio.account}, mas o cliente está cadastrado na conta "
                             f"{row['account']}")
    folder = month_dir(slug, month)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "portfolio.pdf").write_bytes(statement_pdf)
    (folder / "portfolio.json").write_text(json.dumps(portfolio.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "portfolio.txt").write_text(portfolio_to_text(portfolio), encoding="utf-8")
    report, _ = run_profitability(folder, "market", row["profile"])
    return {"reader": reader, "return_pct": report.return_pct, "warnings": portfolio.warnings + report.warnings}


def has_statement(slug: str, month: str | None = None) -> bool:
    return (month_dir(slug, month) / "portfolio.pdf").exists()


def register_client(account: str, name: str, cpf: str, email: str, advisor: dict,
                    risk_profile_pdf: bytes | None = None) -> dict:
    """New client in the advisor's CRM; the suitability PDF is optional and can come later."""
    slug = crm.slugify(name)
    profile = ""
    if risk_profile_pdf:
        folder = crm.CLIENTS_DIR / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "risk_profile.pdf").write_bytes(risk_profile_pdf)
        profile = parse_risk_profile_label(pdf_to_text(folder / "risk_profile.pdf"))
    crm.upsert_client(slug, name.strip(), account.strip(), profile, email, cpf,
                      f"{advisor['name']} ({advisor['code']})", advisor["code"])
    return {"slug": slug, "profile": PROFILE_PT.get(profile, profile)}


def ensure_demo_advisor(email: str, password: str) -> None:
    """The advisor of the demo clients, with the login given by the server's settings."""
    pdf = next(iter(sorted(crm.CLIENTS_DIR.glob("*/*/portfolio.pdf"))), None)
    if pdf:
        portfolio = load_portfolio(pdf.parent)
        crm.set_advisor(email, portfolio.advisor_name, portfolio.advisor_code, password)


def sync_clients() -> int:
    """Register in the CRM every client folder that already has a statement (e.g. the demo clients)."""
    count = 0
    for folder in sorted(crm.CLIENTS_DIR.glob("*/*/portfolio.pdf")):
        slug, risk = folder.parents[1].name, folder.parents[1] / "risk_profile.pdf"
        if not risk.exists():
            continue
        portfolio = load_portfolio(folder.parent)
        crm.upsert_client(slug, portfolio.client_name, portfolio.account, parse_risk_profile_label(pdf_to_text(risk)),
                          advisor=f"{portfolio.advisor_name} ({portfolio.advisor_code})",
                          advisor_code=portfolio.advisor_code)
        letter = folder.parent / "letter.json"
        if letter.exists() and (folder.parent / "letter.pdf").exists():
            doc = json.loads(letter.read_text(encoding="utf-8"))
            current = {c["slug"]: c["status"] for c in crm.clients(folder.parent.name)}
            if current.get(slug) == "pending":
                crm.set_letter(slug, folder.parent.name, "generated" if doc["status"] == "approved" else "needs_review",
                               _cost(doc), len(doc.get("advisor_notes", [])))
        count += 1
    return count


# ------------------------------------------------------------------------ letters

def _cost(doc: dict) -> float:
    return round(sum(a["usage"].get("cost", 0) for a in doc.get("attempts", [])), 4)


def generate_letter(slug: str, month: str | None = None) -> dict:
    """Profitability (if missing) -> Rivet letter -> PDF, with the status saved in the CRM."""
    month = month or current_month()
    folder = month_dir(slug, month)
    start = time.time()
    crm.set_letter(slug, month, "generating")
    try:
        if not (folder / "profitability_market.json").exists():
            run_profitability(folder, "market")
        doc = generate(folder)
        build_pdf(folder)
        status = "generated" if doc["status"] == "approved" else "needs_review"
        crm.set_letter(slug, month, status, _cost(doc), len(doc.get("advisor_notes", [])))
        return {"slug": slug, "status": status, "seconds": round(time.time() - start)}
    except Exception as exc:  # one client's failure never stops the batch
        crm.set_letter(slug, month, "error", error=f"{exc}"[:500])
        return {"slug": slug, "status": "error", "error": str(exc), "trace": traceback.format_exc()}


def generate_batch(slugs: list[str], month: str | None = None, workers: int = BATCH_WORKERS,
                   on_done: Callable[[dict], None] | None = None) -> list[dict]:
    """Generate many letters at once; the macro digest is prepared first so it is shared, not repeated."""
    settings = load_settings()
    load_env()
    period = periods.from_folder(month or current_month())
    macro_digest(macro_report(period), period.letter_date, settings.get("llm", {}).get("model", "gpt-4o-mini"))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(generate_letter, slug, month) for slug in slugs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_done:
                on_done(result)
    return results


def save_letter_edits(slug: str, letter: dict, month: str | None = None) -> None:
    """The advisor edited the text: keep the edit in letter.json and lay out the PDF again."""
    folder = month_dir(slug, month)
    path = folder / "letter.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["letter"], doc["edited_by_advisor"] = letter, True
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    build_pdf(folder)

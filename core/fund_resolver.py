"""Map statement fund names to CVM CNPJs automatically.

A statement only prints the fund's commercial name ("Truxt Long Bias Advisory FIC FIM").
To price it we need the CNPJ, whose daily quota is in the CVM open data. Curating that by
hand does not scale to 300 clients, so new names are resolved here:

1. Already in ``config/fund_registry.json`` (curated or resolved before): use it.
2. Search the CVM registers for funds whose name holds every *distinctive* word of the
   statement name (manager and strategy, ignoring legal words such as FIC, FIM, CP).
3. Exactly one plausible candidate that publishes quotas -> accepted (``status: auto``).
4. No candidate, several close candidates, or a fund without daily quotas (e.g. a FIDC)
   -> a proxy by fund type (equity funds: Ibovespa, others: CDI), ``status: needs_review``
   with the best candidates, so the advisor confirms the fund once.

Every resolution is written back to the registry, so each fund is resolved only once
for the whole client base.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

# Legal and category words: they appear in most fund names, so they do not identify one.
GENERIC_WORDS = {
    "FIC", "FI", "FIF", "FIM", "FIA", "FIRF", "FIDC", "FICFI", "FICFIM", "FICFIA", "IE", "LP",
    "DE", "DA", "DO", "DOS", "DAS", "EM", "E", "COTAS", "FUNDO", "FUNDOS", "INVESTIMENTO",
    "INVESTIMENTOS", "CLASSE", "CLASSES", "RESPONSABILIDADE", "LIMITADA", "MULTIMERCADO",
    "ACOES", "RENDA", "FIXA", "RF", "REF", "DI", "CP", "CREDITO", "PRIVADO", "SIMPLES",
    "REFERENCIADO", "MASTER", "FEEDER", "FINANCEIRO", "FINANCEIROS", "MULTIMERCADOS", "RESP",
}
# Statements abbreviate ("FIC FIM"); the CVM register spells out ("FIF EM COTAS ... MULTIMERCADO").
# Both are reduced to the same concepts before comparing.
CONCEPTS = {
    "FIC": "FIC", "COTAS": "FIC", "FICFI": "FIC", "FICFIM": "FIC", "FICFIA": "FIC",
    "FIM": "FIM", "MULTIMERCADO": "FIM", "MULTIMERCADOS": "FIM",
    "FIA": "FIA", "ACOES": "FIA",
    "FIRF": "RF", "RF": "RF", "RENDA": "RF", "FIXA": "RF",
    "DI": "DI", "REF": "DI", "REFERENCIADO": "DI",
    "CP": "CP", "CREDITO": "CP", "PRIVADO": "CP",
    "FIDC": "FIDC", "MASTER": "MASTER", "SIMPLES": "SIMPLES",
}
ACTIVE_STATUS = "FUNCIONAMENTO"
MIN_SCORE = 0.4     # below this the "match" shares the words but not the fund type
UNKNOWN_TYPE_OVERLAP = 0.6   # score given when the register name states no fund type
MIN_MARGIN = 0.15   # best candidate must beat the runner-up by this much to be auto-accepted


def normalize(name: str) -> list[str]:
    """Upper case, no accents, no punctuation, split into words."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().upper()
    text = text.replace(".", "")   # "F.I.C." -> "FIC"
    return re.sub(r"[^A-Z0-9]+", " ", text).split()


def distinctive_words(name: str) -> list[str]:
    return [w for w in normalize(name) if w not in GENERIC_WORDS]


def proxy_for(sub_class: str) -> str:
    return "IBOV" if sub_class == "equity_fund" else "CDI"


@dataclass
class Resolution:
    name: str
    entry: dict                         # what goes into fund_registry.json
    warning: str = ""                   # shown to the advisor when a review is needed
    candidates: list[dict] = field(default_factory=list)


def _concepts(words: list[str]) -> set[str]:
    return {CONCEPTS[w] for w in words if w in CONCEPTS}


def _score(statement_words: list[str], candidate_name: str) -> float:
    """How well a candidate's name matches the statement name, from about 0 to 1.

    Every candidate already holds all distinctive words; this breaks ties between share
    classes, feeders and master funds of the same manager. It is the share of the
    statement's fund-type concepts (FIC, FIM, CP ...) the candidate has, minus a penalty
    for each distinctive word or concept the candidate adds (e.g. "SHORT", "MASTER")."""
    cand_words = normalize(candidate_name)
    mine, theirs = _concepts(statement_words), _concepts(cand_words)
    if not mine:
        overlap = 1.0
    elif not theirs:
        # Names registered after CVM Resolution 175 are often just "<NAME> FIF", with no
        # type at all: that is unknown, not a mismatch.
        overlap = UNKNOWN_TYPE_OVERLAP
    else:
        overlap = len(mine & theirs) / len(mine)
    extra_words = {w for w in cand_words if w not in GENERIC_WORDS} - set(statement_words)
    extra_concepts = theirs - mine - {"RF", "DI"}   # registers often spell out "RENDA FIXA" for DI funds
    return overlap - 0.25 * len(extra_words) - 0.2 * len(extra_concepts)


def _ranked(matches: pd.DataFrame, words: list[str]) -> pd.DataFrame:
    """Active funds first, then by name score."""
    return (matches.assign(
                ACTIVE=matches["STATUS"].fillna("").str.upper().str.contains(ACTIVE_STATUS),
                SCORE=matches["NAME"].map(lambda n: _score(words, n)))
            .sort_values(["ACTIVE", "SCORE"], ascending=False))


def _as_candidates(ranked: pd.DataFrame) -> list[dict]:
    return [{"cnpj": r.CNPJ, "name": r.NAME, "status": r.STATUS, "score": round(float(r.SCORE), 2)}
            for r in ranked.itertuples()]


def resolve(name: str, sub_class: str, registry: pd.DataFrame,
            has_quotas: Callable[[str], bool]) -> Resolution:
    """Resolve one statement fund name against the CVM registers.

    ``registry`` has CNPJ / NAME / STATUS columns (``market_data._registry_frames``);
    ``has_quotas(cnpj)`` tells whether the fund publishes a daily quota for the period.
    """
    words = normalize(name)
    key = distinctive_words(name)
    proxy = proxy_for(sub_class)

    def fallback(reason: str, candidates: list[dict]) -> Resolution:
        entry = {"proxy": proxy, "status": "needs_review", "auto": True,
                 "note": f"{reason}; {'Ibovespa' if proxy == 'IBOV' else 'CDI'} used as proxy until confirmed"}
        if candidates:
            entry["candidates"] = candidates
        return Resolution(name, entry, f"{name}: {reason}. Confirm the CNPJ in config/fund_registry.json "
                                        f"(proxy {proxy} used meanwhile)", candidates)

    if not key:
        return fallback("name has no distinctive words to search", [])

    names = registry["NAME"].fillna("").map(lambda n: set(normalize(n)))
    matches = registry[names.map(lambda n: all(w in n for w in key))].drop_duplicates(subset=["CNPJ"])
    if matches.empty:
        # Funds get renamed ("Investback" -> "INB"): drop trailing words to list the manager's
        # funds for the advisor, but never accept such a partial match automatically.
        for size in range(len(key) - 1, 0, -1):
            partial = registry[names.map(lambda n: all(w in n for w in key[:size]))].drop_duplicates(subset=["CNPJ"])
            if not partial.empty:
                return fallback("no CVM fund holds the words " + " ".join(key),
                                _ranked(partial, words).head(3).pipe(_as_candidates))
        return fallback("no CVM fund holds the words " + " ".join(key), [])

    ranked = _ranked(matches, words)
    top = _as_candidates(ranked.head(3))

    active = ranked[ranked["ACTIVE"]]
    pool = active if not active.empty else ranked
    best = pool.iloc[0]
    runner_up = pool.iloc[1]["SCORE"] if len(pool) > 1 else None
    if best["SCORE"] < MIN_SCORE:
        return fallback(f"closest CVM fund ({best['NAME']}) looks like a different fund", top)
    if runner_up is not None and best["SCORE"] - runner_up < MIN_MARGIN:
        return fallback(f"{len(pool)} CVM funds match and none stands out", top)
    if not has_quotas(best["CNPJ"]):
        return fallback(f"best match {best['CNPJ']} ({best['NAME']}) publishes no daily quota "
                        "(e.g. FIDC or closed fund)", top)

    entry = {"cnpj": best["CNPJ"], "status": "auto", "auto": True, "matched_name": best["NAME"]}
    if active.empty:
        entry["note"] = f"matched a fund that is not active in the CVM register ({best['STATUS']})"
    warning = f"{name}: matched automatically to {best['CNPJ']} ({best['NAME']})"
    return Resolution(name, entry, warning, top)


def save_registry(path, registry: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

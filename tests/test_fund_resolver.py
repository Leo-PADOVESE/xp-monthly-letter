import pandas as pd

from core import fund_resolver

REGISTRY = pd.DataFrame([
    {"CNPJ": "30.830.162/0001-18", "NAME": "TRUXT LONG BIAS ADVISORY FIC FIM", "STATUS": "EM FUNCIONAMENTO NORMAL"},
    {"CNPJ": "11.111.111/0001-11", "NAME": "TRUXT LONG BIAS MASTER FIM", "STATUS": "EM FUNCIONAMENTO NORMAL"},
    {"CNPJ": "22.222.222/0001-22", "NAME": "TRUXT LONG BIAS ADVISORY FIC FIM", "STATUS": "CANCELADA"},
    {"CNPJ": "33.333.333/0001-33", "NAME": "ALPHA MACRO FIC FIM", "STATUS": "EM FUNCIONAMENTO NORMAL"},
    {"CNPJ": "44.444.444/0001-44", "NAME": "ALPHA GLOBAL FIC FIM", "STATUS": "EM FUNCIONAMENTO NORMAL"},
    {"CNPJ": "35.726.300/0001-37", "NAME": "BRAVE 90 FIC FIDC", "STATUS": "EM FUNCIONAMENTO NORMAL"},
])


def always(_cnpj):
    return True


def test_unique_active_match_is_accepted_automatically():
    r = fund_resolver.resolve("Truxt Long Bias Advisory FIC FIM", "multimarket_fund", REGISTRY, always)
    assert r.entry["cnpj"] == "30.830.162/0001-18"   # active feeder beats the master and the cancelled copy
    assert r.entry["status"] == "auto"


def test_accents_and_punctuation_are_ignored():
    r = fund_resolver.resolve("Truxt Long-Bias Advisory F.I.C. FIM", "multimarket_fund", REGISTRY, always)
    assert r.entry["cnpj"] == "30.830.162/0001-18"


def test_ambiguous_names_fall_back_to_proxy_for_review():
    r = fund_resolver.resolve("Alpha FIC FIM", "multimarket_fund", REGISTRY, always)
    assert r.entry["proxy"] == "CDI" and r.entry["status"] == "needs_review"
    assert {c["cnpj"] for c in r.candidates} == {"33.333.333/0001-33", "44.444.444/0001-44"}


def test_unknown_equity_fund_uses_ibovespa_proxy():
    r = fund_resolver.resolve("Nowhere Capital FIC FIA", "equity_fund", REGISTRY, always)
    assert r.entry["proxy"] == "IBOV" and r.entry["status"] == "needs_review"
    assert "Confirm the CNPJ" in r.warning


def test_fund_without_daily_quotas_is_priced_by_proxy():
    r = fund_resolver.resolve("Brave 90 FIC FIDC", "other_fund", REGISTRY, lambda cnpj: False)
    assert r.entry["proxy"] == "CDI"
    assert r.candidates[0]["cnpj"] == "35.726.300/0001-37"


def test_resolution_is_saved_once(tmp_path, monkeypatch):
    from datetime import date
    from core import market_data
    path = tmp_path / "fund_registry.json"
    monkeypatch.setattr(market_data, "FUND_REGISTRY", path)
    monkeypatch.setattr(market_data, "_registry_frames", lambda: [REGISTRY])
    monkeypatch.setattr(market_data, "fund_has_quotas", lambda cnpj, day: True)
    entry, warning = market_data.fund_entry("Truxt Long Bias Advisory FIC FIM", "multimarket_fund", date(2025, 4, 30))
    assert entry["cnpj"] == "30.830.162/0001-18" and "matched automatically" in warning
    monkeypatch.setattr(market_data, "_registry_frames", lambda: (_ for _ in ()).throw(AssertionError("searched twice")))
    entry, warning = market_data.fund_entry("Truxt Long Bias Advisory FIC FIM", "multimarket_fund", date(2025, 4, 30))
    assert entry["cnpj"] == "30.830.162/0001-18" and warning == ""


def test_feeder_is_preferred_over_master_and_sibling_strategies():
    registry = pd.DataFrame([
        {"CNPJ": "12.282.747/0001-69", "NAME": "STK LONG BIASED FIC DE FUNDOS DE INVESTIMENTO FINANCEIRO DE AÇÕES",
         "STATUS": "Em Funcionamento Normal"},
        {"CNPJ": "12.297.830/0001-01", "NAME": "STK LONG BIASED MASTER FUNDO DE INVESTIMENTO FINANCEIRO EM AÇÕES",
         "STATUS": "Em Funcionamento Normal"},
        {"CNPJ": "14.476.715/0001-20", "NAME": "MANAGER STK LONG BIASED FIF CLASSE DE INVESTIMENTO EM COTAS EM AÇÕES",
         "STATUS": "Em Funcionamento Normal"},
    ])
    r = fund_resolver.resolve("STK Long Biased FIC FIA", "equity_fund", registry, always)
    assert r.entry["cnpj"] == "12.282.747/0001-69"


def test_weak_word_overlap_is_not_a_match():
    # "Brave I" shares the words BRAVE and I with an unrelated, cancelled BDR fund.
    registry = pd.DataFrame([{"CNPJ": "42.870.785/0001-01", "STATUS": "CANCELADA",
                              "NAME": "DNA BRAVE GLOBAL FUNDO DE INVESTIMENTO EM AÇÕES BDR NIVEL I"}])
    r = fund_resolver.resolve("Brave I FIC FIM CP", "multimarket_fund", registry, always)
    assert r.entry["proxy"] == "CDI" and r.entry["status"] == "needs_review"


def test_cnpj_formats_are_unified():
    from core.market_data import format_cnpj
    assert format_cnpj("43917493000131") == format_cnpj("43.917.493/0001-31") == "43.917.493/0001-31"


def test_register_name_without_fund_type_is_not_a_mismatch():
    # Post-Resolution 175 names such as "DYNAMO COUGAR FUNDO DE INVESTIMENTO FINANCEIRO" state no type.
    registry = pd.DataFrame([
        {"CNPJ": "73.232.530/0001-39", "NAME": "DYNAMO COUGAR FUNDO DE INVESTIMENTO FINANCEIRO",
         "STATUS": "Em Funcionamento Normal"},
        {"CNPJ": "37.916.879/0001-26", "NAME": "DYNAMO COUGAR MASTER FUNDO DE INVESTIMENTO FINANCEIRO",
         "STATUS": "Em Funcionamento Normal"},
        {"CNPJ": "44.613.609/0001-01", "NAME": "DYNAMO COUGAR L FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS DE INVESTIMENTO EM AÇÕES",
         "STATUS": "Cancelado"},
    ])
    r = fund_resolver.resolve("Dynamo Cougar FIC FIA", "equity_fund", registry, always)
    assert r.entry["cnpj"] == "73.232.530/0001-39"


def test_renamed_fund_lists_the_managers_funds_for_review():
    registry = pd.DataFrame([{"CNPJ": "37.910.132/0001-60", "NAME": "TREND INB FIC FI RF SIMPLES",
                              "STATUS": "Em Funcionamento Normal"}])
    r = fund_resolver.resolve("Trend Investback FIC FIRF Simples", "fixed_income_fund", registry, always)
    assert r.entry["status"] == "needs_review" and r.entry["proxy"] == "CDI"
    assert r.candidates[0]["cnpj"] == "37.910.132/0001-60"

from pathlib import Path

import pytest

from core import crm
from core.ingestion import IngestionError, portfolio_from_extraction
from core.mailer import MailError, build_message, pdf_password

EXTRACTION = {
    "client_name": "Ana Souza", "account": "123", "snapshot_date": "07/05/2025",
    "advisor_code": "A1", "advisor_name": "Antonio",
    "total_equity": "R$ 110.000,00", "total_invested": "R$ 100.000,00", "cash_available": "R$ 10.000,00",
    "positions": [
        {"section": "Ações", "name": "ITUB4", "market_value": "R$ 40.000,00", "allocation_pct": "40%",
         "quantity": "1000", "last_price": "R$ 40,00", "average_price": "R$ 30,00"},
        {"section": "Fundos de Investimentos", "name": "Fundo X FIC FIRF", "market_value": "R$ 30.000,00"},
        {"section": "Renda Fixa", "name": "CDB BANCO Y", "market_value": "R$ 30.000,00",
         "rate": "110% CDI", "maturity_date": "01/01/2027"},
    ],
}


def test_fallback_extraction_becomes_a_checked_portfolio():
    portfolio = portfolio_from_extraction(EXTRACTION)
    assert [p.asset_class for p in portfolio.positions] == ["stocks", "funds", "fixed_income"]
    assert portfolio.positions[1].sub_class == "fixed_income_fund"
    assert "AI fallback" in portfolio.warnings[-1]


def test_fallback_extraction_that_does_not_add_up_is_rejected():
    bad = dict(EXTRACTION, total_invested="R$ 90.000,00")
    with pytest.raises(IngestionError):
        portfolio_from_extraction(bad)


def test_crm_tracks_the_letter_life_cycle(tmp_path: Path):
    db = tmp_path / "crm.db"
    crm.upsert_client("ana_souza", "Ana Souza", "123", "moderate", "ana@example.com", "123.456.789-00", path=db)
    assert crm.clients("2025-05", path=db)[0]["status"] == "pending"
    crm.set_letter("ana_souza", "2025-05", "generated", 0.11, 2, path=db)
    crm.set_letter("ana_souza", "2025-05", "approved", path=db)
    crm.mark_sent("ana_souza", "2025-05", "ana@example.com", path=db)
    row = crm.clients("2025-05", path=db)[0]
    assert (row["status"], row["cost_usd"], row["cpf"]) == ("sent", 0.11, "12345678900")
    assert crm.slugify("Joaquim Conceição") == "joaquim_conceicao"


def test_pdf_password_and_message(tmp_path: Path):
    assert pdf_password("123.456.789-00") == "123456"
    with pytest.raises(MailError):
        pdf_password("")
    pdf = tmp_path / "carta.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    msg = build_message("ana@example.com", "Sua carta", "Ana", "Antonio", pdf, 6)
    assert msg["To"] == "ana@example.com" and "6 primeiros dígitos" in msg.get_body().get_content()

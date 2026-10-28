import json
import shutil
from pathlib import Path

from pypdf import PdfReader

from core.letter_pdf import MAX_PAGES, build_pdf

CLIENTS = Path(__file__).resolve().parents[1] / "data" / "clients"


def _copy(client: str, tmp_path: Path) -> Path:
    month = tmp_path / client
    month.mkdir()
    for name in ("letter.json", "profitability_market.json"):
        shutil.copy(CLIENTS / client / "2025-05" / name, month / name)
    return month


def test_letters_fit_in_two_pages(tmp_path):
    shipped = sorted(p.parents[1].name for p in CLIENTS.glob("*/2025-05/letter.json"))
    assert "albert_da_silva" in shipped
    for client in shipped:
        out, pages = build_pdf(_copy(client, tmp_path))
        assert pages <= MAX_PAGES, client
        text = "".join(page.extract_text() for page in PdfReader(out).pages)
        letter = json.loads((out.parent / "letter.json").read_text(encoding="utf-8"))
        assert letter["client"]["name"] in text and "+3,95%" in text if client == "albert_da_silva" else True


def test_pdf_can_be_protected_with_a_password(tmp_path):
    out, _ = build_pdf(_copy("albert_da_silva", tmp_path), password="123456")
    reader = PdfReader(out)
    assert reader.is_encrypted
    assert reader.decrypt("123456")

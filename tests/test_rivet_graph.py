"""The letter graph end to end, offline: Rivet runs against a fake OpenAI endpoint.

Checks the wiring (one briefing in, Analyst -> Writer -> Reviewer, three outputs) and that the
Python checks accept a well-formed letter. Needs Node.js and rivet/node_modules.
"""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from core.letter_ai import generate

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "rivet" / "node_modules").exists() or not shutil.which("node"),
                                reason="needs Node.js and rivet/node_modules")

ANALYSIS = {"profile": {"summary_pt": "Perfil moderado."},
            "performance": {"headline_pt": "Mês positivo."},
            "assessment": {"class_views": [{"asset_class": "Ações", "weight": "15,59%", "xp_view": "unfavorable",
                                            "profile_fit_pt": "Crescimento, exposto ao consumo interno."}],
                           "assessment_pt": "Avaliação.", "outlook_pt": "Acompanhar a inflação.",
                           "attention_points": [{"fact_id": "idle_cash", "title_pt": "Saldo parado",
                                                 "text_pt": "Vale conversar com seu assessor sobre o saldo parado."}]}}
LETTER = {"subject_pt": "Sua carta de abril", "greeting_pt": "Prezado Albert,", "opening_pt": "Abril foi positivo.",
          "performance_pt": ["Sua carteira rendeu +3,95% no mês, o equivalente a 374% do CDI. "
                             + "O resultado veio principalmente das ações. " * 40],
          "macro_pt": "A XP projeta a Selic em 15,50% ao fim de 2025.",
          "assessment_pt": "O portfólio de Albert está coerente com o perfil, segundo o digest macro da XP.",
          "attention_points": ANALYSIS["assessment"]["attention_points"],
          "outlook_pt": "Acompanhar a inflação.", "closing_pt": "Estou à disposição."}


class FakeOpenAI(BaseHTTPRequestHandler):
    prompts: list[str] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = json.dumps(body["messages"], ensure_ascii=False)
        FakeOpenAI.prompts.append(text)
        reply = (ANALYSIS if "analyze the client" in text else LETTER if "write the monthly letter" in text
                 else {"approved": True, "issues": []})
        chunk = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                 "choices": [{"index": 0, "delta": {"role": "assistant", "content": json.dumps(reply)},
                              "finish_reason": "stop"}]}
        data = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_openai(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_ENDPOINT", f"http://127.0.0.1:{server.server_port}/v1/chat/completions")
    FakeOpenAI.prompts = []
    yield FakeOpenAI
    server.shutdown()


def test_letter_graph_reads_one_briefing(fake_openai, tmp_path):
    month = tmp_path / "albert" / "2025-05"
    shutil.copytree(ROOT / "data" / "clients" / "albert_da_silva" / "2025-05", month,
                    ignore=shutil.ignore_patterns("letter*", "briefing.json"))
    shutil.copy(ROOT / "data" / "clients" / "albert_da_silva" / "risk_profile.pdf", month.parent)
    doc = generate(month, max_rewrites=0)

    assert len(fake_openai.prompts) == 3                     # Analyst, Writer, Reviewer
    briefing = json.loads((month / "briefing.json").read_text(encoding="utf-8"))
    assert set(briefing) == {"client", "profile", "statement", "results", "portfolio_facts", "macro_digest"}
    assert all("374% do CDI" in prompt for prompt in fake_openai.prompts)   # every step reads the same briefing
    assert doc["status"] == "approved", doc["attempts"][-1]["issues"]
    assert doc["letter"]["class_views"][0]["asset_class"] == "Ações"
    assert doc["letter"]["assessment_pt"].startswith("Seu portfólio")     # third person and jargon tidied
    assert "relatório macro da XP" in doc["letter"]["assessment_pt"]

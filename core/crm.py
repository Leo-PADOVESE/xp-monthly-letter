"""Advisor CRM: clients and the status of each monthly letter, in SQLite.

The files of a client live in data/clients/<slug>/ (risk_profile.pdf) and
data/clients/<slug>/<yyyy-mm>/ (statement, results, letter); the database only keeps the
contact data the statement does not have (e-mail, CPF for the PDF password) and the letter's
life cycle:

    generating -> generated / needs_review  ->  approved  ->  sent
                 \\-> error (the advisor sees why and can retry)
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "crm.db"
CLIENTS_DIR = ROOT / "data" / "clients"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    account TEXT,
    profile TEXT,
    email TEXT,
    cpf TEXT,
    advisor TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS letters (
    slug TEXT NOT NULL REFERENCES clients(slug),
    month TEXT NOT NULL,
    status TEXT NOT NULL,
    cost_usd REAL,
    notes INTEGER,
    error TEXT,
    updated_at TEXT NOT NULL,
    sent_to TEXT,
    sent_at TEXT,
    PRIMARY KEY (slug, month)
);
"""

STATUS_PT = {"generating": "Gerando...", "generated": "Pronta para revisão", "needs_review": "Revisar com atenção",
             "approved": "Aprovada", "sent": "Enviada", "error": "Erro", "pending": "Não gerada"}


def slugify(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(path: Path = DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_client(slug: str, name: str, account: str = "", profile: str = "", email: str = "", cpf: str = "",
                  advisor: str = "", path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute(
            """INSERT INTO clients (slug, name, account, profile, email, cpf, advisor, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name, account=excluded.account,
                 profile=excluded.profile, advisor=excluded.advisor,
                 email=COALESCE(NULLIF(excluded.email, ''), clients.email),
                 cpf=COALESCE(NULLIF(excluded.cpf, ''), clients.cpf)""",
            (slug, name, account, profile, email, re.sub(r"\D", "", cpf), advisor, _now()))


def update_contact(slug: str, email: str, cpf: str, path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute("UPDATE clients SET email = ?, cpf = ? WHERE slug = ?", (email.strip(), re.sub(r"\D", "", cpf), slug))


def clients(month: str, path: Path = DB_PATH) -> list[dict]:
    """Every client with this month's letter status ("pending" when not generated)."""
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT c.*, COALESCE(l.status, 'pending') AS status, l.cost_usd, l.notes, l.error, l.sent_to, l.sent_at
               FROM clients c LEFT JOIN letters l ON l.slug = c.slug AND l.month = ?
               ORDER BY c.name""", (month,)).fetchall()
    return [dict(r) for r in rows]


def client(slug: str, path: Path = DB_PATH) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM clients WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def set_letter(slug: str, month: str, status: str, cost_usd: float | None = None, notes: int | None = None,
               error: str | None = None, path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute(
            """INSERT INTO letters (slug, month, status, cost_usd, notes, error, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug, month) DO UPDATE SET status=excluded.status,
                 cost_usd=COALESCE(excluded.cost_usd, letters.cost_usd),
                 notes=COALESCE(excluded.notes, letters.notes), error=excluded.error, updated_at=excluded.updated_at""",
            (slug, month, status, cost_usd, notes, error, _now()))


def mark_sent(slug: str, month: str, email: str, path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute("UPDATE letters SET status = 'sent', sent_to = ?, sent_at = ?, updated_at = ? "
                     "WHERE slug = ? AND month = ?", (email, _now(), _now(), slug, month))


def reset_interrupted(path: Path = DB_PATH) -> None:
    """Letters left "generating" by a server restart go back to the queue as errors the advisor can retry."""
    with connect(path) as conn:
        conn.execute("UPDATE letters SET status = 'error', error = 'Geração interrompida (servidor reiniciou)', "
                     "updated_at = ? WHERE status = 'generating'", (_now(),))

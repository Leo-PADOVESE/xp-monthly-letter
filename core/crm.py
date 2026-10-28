"""Advisor CRM: clients and the status of each monthly letter, in SQLite.

The files of a client live in data/clients/<slug>/ (risk_profile.pdf) and
data/clients/<slug>/<yyyy-mm>/ (statement, results, letter); the database only keeps the
contact data the statement does not have (e-mail, CPF for the PDF password) and the letter's
life cycle:

    generating -> generated / needs_review  ->  approved  ->  sent
                 \\-> error (the advisor sees why and can retry)
"""

from __future__ import annotations

import hashlib
import re
import secrets
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
    advisor_code TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisors (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL
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
    if "advisor_code" not in {r["name"] for r in conn.execute("PRAGMA table_info(clients)")}:
        conn.execute("ALTER TABLE clients ADD COLUMN advisor_code TEXT")  # databases created before advisor login
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_client(slug: str, name: str, account: str = "", profile: str = "", email: str = "", cpf: str = "",
                  advisor: str = "", advisor_code: str = "", path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute(
            """INSERT INTO clients (slug, name, account, profile, email, cpf, advisor, advisor_code, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name,
                 account=COALESCE(NULLIF(excluded.account, ''), clients.account),
                 profile=COALESCE(NULLIF(excluded.profile, ''), clients.profile),
                 advisor=COALESCE(NULLIF(excluded.advisor, ''), clients.advisor),
                 advisor_code=COALESCE(NULLIF(excluded.advisor_code, ''), clients.advisor_code),
                 email=COALESCE(NULLIF(excluded.email, ''), clients.email),
                 cpf=COALESCE(NULLIF(excluded.cpf, ''), clients.cpf)""",
            (slug, name, account, profile, email, re.sub(r"\D", "", cpf), advisor, advisor_code, _now()))


def update_contact(slug: str, email: str, cpf: str, account: str | None = None, path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.execute("UPDATE clients SET email = ?, cpf = ?, account = COALESCE(?, account) WHERE slug = ?",
                     (email.strip(), re.sub(r"\D", "", cpf), account, slug))


# ------------------------------------------------------------------- advisors

def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def set_advisor(email: str, name: str, code: str, password: str, path: Path = DB_PATH) -> None:
    salt = secrets.token_hex(16)
    with connect(path) as conn:
        conn.execute(
            """INSERT INTO advisors (email, name, code, salt, password_hash) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET name=excluded.name, code=excluded.code, salt=excluded.salt,
                 password_hash=excluded.password_hash""",
            (email.strip().lower(), name, code, salt, _hash(password, salt)))


def login(email: str, password: str, path: Path = DB_PATH) -> dict | None:
    """The advisor (email, name, code) when the password matches, else None."""
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM advisors WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row and secrets.compare_digest(row["password_hash"], _hash(password, row["salt"])):
        return {"email": row["email"], "name": row["name"], "code": row["code"]}
    return None


def clients(month: str, advisor_code: str | None = None, path: Path = DB_PATH) -> list[dict]:
    """Every client (of one advisor, when given) with this month's letter status ("pending" when not generated)."""
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT c.*, COALESCE(l.status, 'pending') AS status, l.cost_usd, l.notes, l.error, l.sent_to, l.sent_at
               FROM clients c LEFT JOIN letters l ON l.slug = c.slug AND l.month = ?
               WHERE ? IS NULL OR c.advisor_code = ?
               ORDER BY c.name""", (month, advisor_code, advisor_code)).fetchall()
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


def delete_client(slug: str, path: Path = DB_PATH) -> None:
    """Remove the client, its letters and its files (statements, results, letters)."""
    import shutil

    with connect(path) as conn:
        conn.execute("DELETE FROM letters WHERE slug = ?", (slug,))
        conn.execute("DELETE FROM clients WHERE slug = ?", (slug,))
    if path == DB_PATH:
        shutil.rmtree(CLIENTS_DIR / slug, ignore_errors=True)

"""Send an approved letter by e-mail, with the PDF protected by the client's CPF digits.

SMTP settings come from the environment (on the server, from its secrets; locally, from .env):
SMTP_USER and SMTP_PASSWORD (for Gmail, an app password), optional SMTP_HOST, SMTP_PORT and
SMTP_FROM. Nothing is sent unless an advisor approved the letter on the platform.
"""

from __future__ import annotations

import os
import re
import shutil
import smtplib
import tempfile
from email.message import EmailMessage
from pathlib import Path

from core.letter_pdf import protect


class MailError(RuntimeError):
    pass


def pdf_password(cpf: str, digits: int = 6) -> str:
    numbers = re.sub(r"\D", "", cpf or "")
    if len(numbers) < digits:
        raise MailError("CPF do cliente não cadastrado: necessário para a senha do PDF")
    return numbers[:digits]


def build_message(to: str, subject: str, first_name: str, advisor: str, pdf: Path, password_digits: int) -> EmailMessage:
    sender = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(
        f"Olá, {first_name},\n\n"
        "Segue em anexo a sua carta mensal com o desempenho da carteira, o cenário econômico da XP e "
        "alguns pontos para conversarmos.\n\n"
        f"Por segurança, o PDF é protegido por senha: os {password_digits} primeiros dígitos do seu CPF.\n\n"
        f"Fico à disposição,\n{advisor}\nXP Investimentos\n")
    msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)
    return msg


def send_letter(month_dir: Path, to: str, cpf: str, subject: str, first_name: str, advisor: str,
                password_digits: int = 6) -> None:
    """Protect a copy of letter.pdf with the CPF digits and send it."""
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "")  # Gmail shows app passwords in groups of 4
    if not (user and password):
        raise MailError("Envio de e-mail não configurado no servidor (SMTP_USER e SMTP_PASSWORD)")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / f"carta_mensal_{month_dir.name}.pdf"
        shutil.copy(month_dir / "letter.pdf", pdf)
        protect(pdf, pdf_password(cpf, password_digits))
        msg = build_message(to, subject, first_name, advisor, pdf, password_digits)
        host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587"))
        try:
            if port == 465:                              # implicit TLS (SMTPS)
                smtp = smtplib.SMTP_SSL(host, port, timeout=20)
            else:                                        # 587: plain connection upgraded with STARTTLS
                smtp = smtplib.SMTP(host, port, timeout=20)
                smtp.starttls()
            with smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise MailError("O Gmail recusou o login: SMTP_PASSWORD precisa ser uma senha de app de 16 letras "
                            "(myaccount.google.com/apppasswords), não a senha da conta") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise MailError(f"O servidor de e-mail recusou o destinatário {to}") from exc
        except (TimeoutError, ConnectionError, smtplib.SMTPServerDisconnected) as exc:
            raise MailError(f"Sem conexão com {host}:{port} ({exc.__class__.__name__}). O servidor pode estar "
                            "bloqueando a porta SMTP (o plano Free do Render bloqueia 25, 465 e 587): "
                            "confira se o serviço está num plano pago") from exc

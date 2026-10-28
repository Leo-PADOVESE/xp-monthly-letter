"""Advisor platform: login, client CRM, and the monthly reports (letter generation, review and e-mail).

    streamlit run app/streamlit_app.py

On the server the OpenAI key, the SMTP credentials and the advisor login (ADVISOR_EMAIL, APP_PASSWORD)
come from environment variables set as secrets; locally they come from .env.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import crm, pipeline  # noqa: E402
from core.letter_ai import load_env  # noqa: E402
from core.mailer import MailError, send_letter  # noqa: E402
from core.profitability import load_settings  # noqa: E402

load_env()
SETTINGS = load_settings()
MONTH = pipeline.current_month()
PROFILE_PT = {"conservative": "Conservador", "moderate": "Moderado", "aggressive": "Arrojado"}
STATUS_ICON = {"pending": "⚪", "generating": "⏳", "generated": "🟢", "needs_review": "🟠", "approved": "✅",
               "sent": "📨", "error": "🔴"}
ADVISOR_EMAIL = os.environ.get("ADVISOR_EMAIL", "assessor@xpi.com.br")
# Locally (no APP_PASSWORD in .env) the demo password is xp123; on Render APP_PASSWORD is required.
APP_PASSWORD = os.environ.get("APP_PASSWORD") or ("" if os.environ.get("RENDER") else "xp123")

st.set_page_config(page_title="XP · Assessor", page_icon="📈", layout="wide")
st.markdown("""
<style>
  :root {--xp-black:#141414; --xp-yellow:#FFC709; --xp-grey:#9A9A9A;}
  .stApp, [data-testid="stSidebar"] {background: var(--xp-black);}
  [data-testid="stSidebar"] {border-right: 3px solid var(--xp-yellow);}
  header[data-testid="stHeader"] {background: transparent;}
  .block-container {padding-top: 2.2rem;}
  .xp-logo {font-weight: 900; color: #fff; letter-spacing: -2px; line-height: 1;
      font-family: "Arial Black", Arial, sans-serif;}
  .xp-logo small {display: block; font-size: .22em; letter-spacing: 4px; font-weight: 600; color: #fff;
      margin-top: 6px;}
  .xp-advisor {font-weight: 800 !important; color: #fff; font-size: 2rem !important; line-height: 1.2;
      margin: 0 !important;}
  .xp-advisor-sub {color: var(--xp-grey); font-size: .85rem; margin: 2px 0 8px 0;}
  .xp-title {font-weight: 800; color: #fff; font-size: 1.25rem; margin: 18px 0 4px 0;}
  .xp-rule {height: 2px; background: var(--xp-yellow); width: 48px; margin: 0 0 14px 0;}
  button[kind^="primary"] {background: var(--xp-yellow) !important; border: 0 !important;}
  button[kind^="primary"], button[kind^="primary"] p {color: var(--xp-black) !important; font-weight: 700;}
  button[kind^="secondary"], div.stDownloadButton > button {background: transparent; color: #fff;
      border: 1px solid #3A3A3A;}
  /* sidebar menu: plain text items, the selected one in yellow with a bar */
  [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {display: none;}
  [data-testid="stSidebar"] [data-testid="stRadioOption"] {padding: 10px 14px; border-left: 3px solid transparent;
      margin: 2px 0; width: 100%;}
  [data-testid="stSidebar"] [data-testid="stRadioOption"] p {font-size: 1.05rem; font-weight: 600; color: #fff;}
  [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {border-left-color: var(--xp-yellow);
      background: #1F1F1F;}
  [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {color: var(--xp-yellow);}
  [data-testid="stSidebar"] [role="radiogroup"], [data-testid="stSidebar"] [role="radiogroup"] > div,
  [data-testid="stSidebar"] [data-testid="stRadio"] > div {width: 100%;}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ server state

@st.cache_resource
def boot() -> int:
    """Once per server start: the demo advisor's login, and the clients already in data/clients."""
    crm.reset_interrupted()
    if APP_PASSWORD:
        pipeline.ensure_demo_advisor(ADVISOR_EMAIL, APP_PASSWORD)
    return pipeline.sync_clients()


@st.cache_resource
def jobs() -> dict:
    """Batches run in a server thread, so the advisor can leave the page (or close it) while letters are written."""
    return {"current": None}


def start_batch(slugs: list[str], workers: int) -> None:
    job = {"total": len(slugs), "done": [], "start": time.time(), "end": None}

    def run() -> None:
        try:
            pipeline.generate_batch(slugs, MONTH, workers, job["done"].append)
        finally:
            job["end"] = time.time()

    jobs()["current"] = job
    threading.Thread(target=run, daemon=True).start()


def pdf_pages(path: Path) -> list:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return [doc[i].render(scale=1.6).to_pil() for i in range(len(doc))]
    finally:
        doc.close()


def letter_doc(slug: str) -> dict | None:
    path = pipeline.month_dir(slug, MONTH) / "letter.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def title(text: str) -> None:
    st.markdown(f'<p class="xp-title">{text}</p><div class="xp-rule"></div>', unsafe_allow_html=True)


def mask_cpf(cpf: str | None) -> str:
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**" if cpf and len(cpf) == 11 else "—"


# ------------------------------------------------------------------------ login

def login_page() -> None:
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] {display:none;}"
                ".stTextInput input {background:#fff; color:#141414; height:46px;}"
                ".stTextInput input::placeholder {color:#8A8A8A;}"
                ".stTextInput [data-baseweb='input'] > div, .stTextInput button {background:#fff; color:#141414;}"
                ".stTextInput [data-baseweb='input'], .stTextInput [data-baseweb='base-input'] {background:#fff;"
                " border:0; border-radius:4px;}</style>", unsafe_allow_html=True)
    _, center, _ = st.columns([1.3, 1, 1.3])
    with center:
        st.markdown('<div style="height:14vh"></div><div class="xp-logo" style="font-size:5.5rem; text-align:center">'
                    'XP<small>INVESTIMENTOS</small></div><div style="height:40px"></div>', unsafe_allow_html=True)
        with st.form("login", border=False):
            email = st.text_input("E-mail", placeholder="E-mail", label_visibility="collapsed")
            password = st.text_input("Senha", placeholder="Senha", type="password", label_visibility="collapsed")
            if st.form_submit_button("Entrar", type="primary", width="stretch"):
                advisor = crm.login(email, password)
                if advisor:
                    st.session_state.advisor = advisor
                    st.rerun()
                st.error("E-mail ou senha incorretos.")
        if not APP_PASSWORD:
            st.error("Login não configurado no servidor (APP_PASSWORD).")


boot()
if "advisor" not in st.session_state:
    login_page()
    st.stop()

ADVISOR = st.session_state.advisor
rows = crm.clients(MONTH, ADVISOR["code"])

with st.sidebar:
    st.markdown('<div class="xp-logo" style="font-size:2.4rem">XP<small>INVESTIMENTOS</small></div>'
                '<div style="height:28px"></div>', unsafe_allow_html=True)
    page = st.radio("Menu", ["Clientes", "Relatórios"], label_visibility="collapsed")
    st.markdown('<div style="height:40vh"></div>', unsafe_allow_html=True)
    if st.button("Sair", width="stretch"):
        del st.session_state.advisor
        st.rerun()

st.markdown(f'<div class="xp-advisor">{ADVISOR["name"]}</div><div class="xp-advisor-sub">Assessor de investimentos · '
            f'{ADVISOR["code"]}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------- clientes

@st.dialog("Cadastrar novo cliente")
def new_client() -> None:
    with st.form("new_client", border=False):
        account = st.text_input("Código da conta")
        name = st.text_input("Nome completo")
        cpf = st.text_input("CPF")
        email = st.text_input("E-mail")
        suitability = st.file_uploader("Suitability (PDF, opcional)", type="pdf")
        if st.form_submit_button("Cadastrar", type="primary", width="stretch"):
            checks = [(account.strip(), "o código da conta"), (name.strip(), "o nome"),
                      (len(re.sub(r"\D", "", cpf)) == 11, "um CPF com 11 dígitos"),
                      (re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()), "um e-mail válido")]
            problems = [message for ok, message in checks if not ok]
            if problems:
                st.error("Informe " + ", ".join(problems) + ".")
                return
            if crm.client(crm.slugify(name)):
                st.error("Já existe um cliente com esse nome.")
                return
            try:
                pipeline.register_client(account, name, cpf, email, ADVISOR,
                                         suitability.getvalue() if suitability else None)
            except Exception as exc:
                st.error(f"Não foi possível ler o suitability: {exc}")
                return
            st.rerun()


@st.dialog("Editar cliente")
def edit_client(row: dict) -> None:
    with st.form("edit_client", border=False):
        account = st.text_input("Código da conta", row["account"] or "")
        st.text_input("Nome completo", row["name"], disabled=True)
        cpf = st.text_input("CPF", "", placeholder="cadastrado (deixe em branco para manter)" if row["cpf"] else "")
        email = st.text_input("E-mail", row["email"] or "")
        suitability = st.file_uploader("Suitability (PDF)", type="pdf")
        if st.form_submit_button("Salvar", type="primary", width="stretch"):
            crm.update_contact(row["slug"], email, cpf or row["cpf"] or "", account.strip() or None)
            if suitability:
                try:
                    pipeline.register_client(account or row["account"], row["name"], cpf or row["cpf"] or "",
                                             email, ADVISOR, suitability.getvalue())
                except Exception as exc:
                    st.error(f"Não foi possível ler o suitability: {exc}")
                    return
            st.rerun()


if page == "Clientes":
    head, button = st.columns([5, 1], vertical_alignment="bottom")
    with head:
        title("Clientes")
    if button.button("+ Novo cliente", type="primary", width="stretch"):
        new_client()

    table = st.dataframe(
        [{"Conta": r["account"], "Cliente": r["name"], "Perfil": PROFILE_PT.get(r["profile"], "—"),
          "CPF": mask_cpf(r["cpf"]), "E-mail": r["email"] or "—",
          "Carta do mês": f"{STATUS_ICON[r['status']]} {crm.STATUS_PT[r['status']]}"} for r in rows],
        width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="clients_table")
    picked = table.selection.rows
    st.caption(f"{len(rows)} clientes · selecione uma linha para editar")
    if picked and st.button(f"Editar {rows[picked[0]]['name']}"):
        edit_client(rows[picked[0]])


# ------------------------------------------------------------------- relatórios

@st.fragment(run_every=3)
def batch_progress() -> None:
    job = jobs()["current"]
    if not job:
        return
    done, total = job["done"], job["total"]
    elapsed = (job["end"] or time.time()) - job["start"]
    st.progress(len(done) / total, f"{len(done)} de {total} prontas · {elapsed:.0f} s")
    for r in done:
        st.write(f"{STATUS_ICON[r['status']]} {crm.client(r['slug'])['name']}: {crm.STATUS_PT[r['status']]}"
                 + (f" em {r['seconds']} s" if r.get("seconds") else "")
                 + (f" — {r['error'][:200]}" if r.get("error") else ""))
    if job["end"]:
        st.success("Lote concluído. Revise na aba **Revisar e enviar**.")
        if not st.session_state.get(f"seen_{job['start']}"):
            st.session_state[f"seen_{job['start']}"] = True
            st.rerun(scope="app")


def generate_tab() -> None:
    ready = [r for r in rows if pipeline.has_statement(r["slug"], MONTH)]
    missing = [r for r in rows if r not in ready]
    if missing:
        with st.expander(f"Extrato do mês pendente: {len(missing)} cliente(s)"):
            chosen = {r["name"]: r for r in missing}
            row = chosen[st.selectbox("Cliente", list(chosen))]
            statement = st.file_uploader("Extrato XP do mês (PDF)", type="pdf", key="statement")
            if st.button("Ler extrato e calcular rentabilidade", type="primary", disabled=not statement):
                with st.spinner("Lendo o extrato e buscando cotações (Yahoo, CVM, Banco Central)..."):
                    try:
                        info = pipeline.add_statement(row["slug"], statement.getvalue(), MONTH)
                        st.success(f"Rentabilidade no mês: {info['return_pct']:+.2f}%.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    if not ready:
        st.info("Nenhum cliente com extrato do mês.")
        return
    names = {f"{STATUS_ICON[r['status']]} {r['name']}": r["slug"] for r in ready}
    pending = [k for k, r in zip(names, ready) if r["status"] in ("pending", "error")]
    selected = st.multiselect("Clientes", list(names), default=pending or list(names))
    job = jobs()["current"]
    running = bool(job and not job["end"])
    if st.button(f"Gerar {len(selected)} carta(s)", type="primary", disabled=running or not selected):
        start_batch([names[k] for k in selected], pipeline.BATCH_WORKERS)
        st.rerun()
    if running:
        st.caption("As cartas estão sendo escritas no servidor. Pode trocar de página: o lote continua.")
    batch_progress()


def review_tab() -> None:
    ready = [r for r in rows if r["status"] in ("generated", "needs_review", "approved", "sent")]
    if not ready:
        st.info("Nenhuma carta gerada ainda.")
        return
    labels = {f"{STATUS_ICON[r['status']]} {r['name']} · {crm.STATUS_PT[r['status']]}": r for r in ready}
    row = labels[st.selectbox("Carta", list(labels))]
    folder = pipeline.month_dir(row["slug"], MONTH)
    doc = letter_doc(row["slug"])

    left, right = st.columns([3, 2])
    with left:
        for image in pdf_pages(folder / "letter.pdf"):
            st.image(image, width="stretch")
    with right:
        st.download_button("Baixar PDF", (folder / "letter.pdf").read_bytes(), f"carta_{row['slug']}_{MONTH}.pdf",
                           "application/pdf", width="stretch")
        notes = doc.get("advisor_notes", [])
        st.markdown(f"**Observações do revisor (IA):** {len(notes) or 'nenhuma'}")
        for n in notes:
            st.warning(f"**{n.get('rule', '')}** · “{n.get('quote', '')}”\n\n{n.get('problem', '')}\n\n"
                       f"*Sugestão:* {n.get('fix', '')}")
        st.caption(f"Checagens automáticas: números conferidos com os dados, sem promessa de retorno, sugestões "
                   f"dentro das regras. Custo: US$ {row['cost_usd'] or 0:.3f}.")

        with st.expander("Editar texto da carta"):
            letter = doc["letter"]
            with st.form("edit"):
                letter["opening_pt"] = st.text_area("Abertura", letter.get("opening_pt", ""))
                letter["performance_pt"] = [st.text_area(f"Desempenho {i + 1}", p, height=140)
                                            for i, p in enumerate(letter.get("performance_pt", []))]
                letter["macro_pt"] = st.text_area("Cenário econômico", letter.get("macro_pt", ""), height=120)
                for i, s in enumerate(letter.get("suggestions", [])):
                    s["text_pt"] = st.text_area(f"Sugestão {i + 1}: {s.get('title_pt', '')}", s.get("text_pt", ""))
                letter["outlook_pt"] = st.text_area("O que esperar", letter.get("outlook_pt", ""))
                if st.form_submit_button("Salvar e refazer o PDF"):
                    pipeline.save_letter_edits(row["slug"], letter, MONTH)
                    st.rerun()

        st.divider()
        if row["status"] in ("generated", "needs_review"):
            if st.button("Aprovar carta", type="primary", width="stretch"):
                crm.set_letter(row["slug"], MONTH, "approved")
                st.rerun()
        else:
            st.success(crm.STATUS_PT[row["status"]] + (f" para {row['sent_to']} em {row['sent_at']}"
                                                         if row["status"] == "sent" else ""))
        if row["status"] in ("approved", "sent"):
            to = st.text_input("Enviar para", row["email"] or "")
            if st.button("Enviar por e-mail", width="stretch", disabled=not to):
                try:
                    with st.spinner("Protegendo o PDF com o CPF e enviando..."):
                        send_letter(folder, to, row["cpf"] or "", doc["letter"].get("subject_pt", "Sua carta mensal"),
                                    doc["client"]["first_name"], doc["client"].get("advisor_name") or "Seu assessor",
                                    SETTINGS.get("delivery", {}).get("pdf_password_cpf_digits", 6))
                    crm.mark_sent(row["slug"], MONTH, to)
                    st.success(f"Enviada para {to}. Senha do PDF: os primeiros dígitos do CPF.")
                except (MailError, OSError) as exc:
                    st.error(str(exc))


if page == "Relatórios":
    title(f"Relatórios · carta de {SETTINGS['letter_date']:%d/%m/%Y}")
    generate, review = st.tabs(["Gerar cartas", "Revisar e enviar"])
    with generate:
        generate_tab()
    with review:
        review_tab()

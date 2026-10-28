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

from core import crm, macro_panel, periods, pipeline  # noqa: E402
from core.letter_ai import load_env  # noqa: E402
from core.mailer import MailError, send_letter  # noqa: E402
from core.profitability import load_settings  # noqa: E402

load_env()
SETTINGS = load_settings()
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
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


def start_batch(slugs: list[str], month: str, workers: int) -> None:
    job = {"total": len(slugs), "done": [], "start": time.time(), "end": None}

    def run() -> None:
        try:
            pipeline.generate_batch(slugs, month, workers, job["done"].append)
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


def month_label(period: periods.Period) -> str:
    return f"{MONTHS_PT[period.reference.month - 1]}/{period.reference:%Y}"


def download(label: str, path: Path, name: str, key: str) -> None:
    st.download_button(label, path.read_bytes(), name, "application/pdf", key=key, width="stretch")


def format_cpf(cpf: str | None) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if cpf and len(cpf) == 11 else "—"


# ------------------------------------------------------------------------ login

def login_page() -> None:
    st.markdown("<style>[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] {display:none;}"
                "[data-testid='stTextInputRootElement'] {background:#fff; border:0; border-radius:4px;}"
                "[data-testid='stTextInputRootElement'] input {background:#fff; color:#141414; height:46px;}"
                "[data-testid='stTextInputRootElement'] input::placeholder {color:#8A8A8A;}"
                "[data-testid='stTextInputRootElement'] input:-webkit-autofill {-webkit-box-shadow:0 0 0 40px #fff inset;"
                " -webkit-text-fill-color:#141414;}"
                "[data-testid='stTextInputRootElement'] button {background:transparent; color:#141414;}"
                "</style>", unsafe_allow_html=True)
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
                    st.query_params["s"] = crm.session_token(advisor["email"])
                    st.rerun()
                st.error("E-mail ou senha incorretos.")
        if not APP_PASSWORD:
            st.error("Login não configurado no servidor (APP_PASSWORD).")


boot()
if "advisor" not in st.session_state and (advisor := crm.advisor_from_token(st.query_params.get("s", ""))):
    st.session_state.advisor = advisor            # page reload: the signed token in the URL keeps the login
if "advisor" not in st.session_state:
    login_page()
    st.stop()

ADVISOR = st.session_state.advisor
MONTH = st.session_state.setdefault("folder",
                                     st.query_params["m"] if re.fullmatch(r"\d{4}-\d{2}", st.query_params.get("m", ""))
                                     else pipeline.current_month())   # letters' folder, e.g. 2025-05
PERIOD = periods.from_folder(MONTH)
rows = crm.clients(MONTH, ADVISOR["code"])

with st.sidebar:
    st.markdown('<div class="xp-logo" style="font-size:2.4rem">XP<small>INVESTIMENTOS</small></div>'
                '<div style="height:28px"></div>', unsafe_allow_html=True)
    pages = ["Macro", "Clientes", "Relatórios"]
    page = st.radio("Menu", pages, index=pages.index(st.query_params.get("p", "Macro")) if
                    st.query_params.get("p") in pages else 0, label_visibility="collapsed")
    st.query_params["p"] = page
    st.markdown('<div style="height:40vh"></div>', unsafe_allow_html=True)
    if st.button("Sair", width="stretch"):
        del st.session_state.advisor
        st.query_params.clear()
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
        cpf = st.text_input("CPF", format_cpf(row["cpf"]) if row["cpf"] else "")
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


@st.dialog("Documentos do cliente", width="large")
def client_documents(row: dict) -> None:
    folder = crm.CLIENTS_DIR / row["slug"]
    st.markdown(f"**{row['name']}** · conta {row['account']}")
    suitability = folder / "risk_profile.pdf"
    st.markdown("**Suitability**")
    if suitability.exists():
        download("Baixar suitability", suitability, f"suitability_{row['slug']}.pdf", "doc_suit")
    else:
        st.caption("Não anexado. Use Editar para anexar.")
    months = sorted((p for p in folder.glob("*/portfolio.pdf")), reverse=True)
    st.markdown("**Extratos e cartas**")
    if not months:
        st.caption("Nenhum extrato ainda. Anexe em Relatórios.")
    for statement in months:
        period = periods.from_folder(statement.parent.name)
        label, left, right = st.columns([2, 2, 2], vertical_alignment="center")
        label.write(f"Referência {month_label(period)}")
        with left:
            download("Extrato", statement, f"extrato_{row['slug']}_{period.key}.pdf", f"st_{period.key}")
        letter = statement.parent / "letter.pdf"
        with right:
            if letter.exists():
                download("Carta", letter, f"carta_{row['slug']}_{period.key}.pdf", f"lt_{period.key}")
            else:
                st.caption("Carta não gerada")


@st.dialog("Excluir cliente")
def delete_client(row: dict) -> None:
    st.write(f"Excluir **{row['name']}** (conta {row['account']})? O cadastro, os extratos e as cartas desse cliente "
             "serão apagados. Essa ação não pode ser desfeita.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancelar", width="stretch"):
        st.rerun()
    if confirm.button("Excluir", type="primary", width="stretch"):
        crm.delete_client(row["slug"])
        st.rerun()


if page == "Clientes":
    head, button = st.columns([5, 1], vertical_alignment="bottom")
    with head:
        title("Clientes")
    if button.button("+ Novo cliente", type="primary", width="stretch"):
        new_client()

    table = st.dataframe(
        [{"Conta": r["account"], "Cliente": r["name"], "Perfil": PROFILE_PT.get(r["profile"], "—"),
          "CPF": format_cpf(r["cpf"]), "E-mail": r["email"] or "—"} for r in rows],
        width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="clients_table")
    picked = table.selection.rows
    st.caption(f"{len(rows)} clientes · selecione uma linha para ver documentos, editar ou excluir")
    if picked:
        chosen = rows[picked[0]]
        docs, edit, remove, _ = st.columns([1.2, 1, 1, 3])
        if docs.button("Documentos", width="stretch"):
            client_documents(chosen)
        if edit.button("Editar", width="stretch"):
            edit_client(chosen)
        if remove.button("Excluir", width="stretch"):
            delete_client(chosen)


# ------------------------------------------------------------------------ macro

@st.cache_data(ttl=6 * 3600, show_spinner="Buscando dados de mercado (Yahoo Finance e Banco Central)...")
def macro_data(start, end, month_start) -> dict:
    data = {name: macro_panel.index_series(name, start, end) for name in macro_panel.INDICES}
    changes = {name: macro_panel.month_change(s, month_start, end) if s is not None else None
               for name, s in data.items()}
    rates = {"Selic meta (% a.a.)": macro_panel.rate_series(macro_panel.SGS_SELIC_TARGET, start, end, "Selic"),
             "IPCA 12 meses (%)": macro_panel.rate_series(macro_panel.SGS_IPCA_12M, start, end, "IPCA 12m")}
    return {"indices": data, "changes": changes, "rates": rates}


def macro_page() -> None:
    head, pick = st.columns([3, 1], vertical_alignment="bottom")
    with head:
        title("Macro")
    options = periods.recent(count=24)
    keys = [p.key for p in options]
    default = keys.index(PERIOD.key) if PERIOD.key in keys else 0
    period = options[pick.selectbox("Mês de referência", range(len(options)), index=default,
                                    format_func=lambda i: month_label(options[i]), key="macro_month")]

    start, end = macro_panel.window(period.end)
    data = macro_data(start, end, period.start)
    cols = st.columns(len(data["changes"]))
    for col, (name, change) in zip(cols, data["changes"].items()):
        col.metric(f"{name} no mês", "—" if change is None else f"{change * 100:+.2f}%".replace(".", ","))
    left, right = st.columns(2)
    charts = list(data["indices"].items()) + list(data["rates"].items())
    for i, (name, series) in enumerate(charts):
        with (left if i % 2 == 0 else right):
            st.markdown(f"**{name}** · 12 meses")
            if series is None or series.empty:
                st.caption("Sem dados disponíveis agora.")
            else:
                st.line_chart(series, color="#FFC709", height=220)

    title("Macro research XP")
    with st.expander("Anexar research do mês"):
        target = st.selectbox("Mês de referência do research", range(len(options)), index=default,
                              format_func=lambda i: month_label(options[i]), key="research_month")
        upload = st.file_uploader("Research (PDF)", type="pdf", key="research_pdf")
        if st.button("Salvar research", type="primary", disabled=not upload):
            periods.MACRO_DIR.mkdir(parents=True, exist_ok=True)
            options[target].macro_report.write_bytes(upload.getvalue())
            st.success(f"Research de {month_label(options[target])} salvo.")
            st.rerun()
    reports = sorted(periods.MACRO_DIR.glob("*.pdf"), reverse=True)
    if not reports:
        st.caption("Nenhum research anexado.")
    for report in reports:
        p = periods.from_key(report.stem)
        name, button = st.columns([4, 1], vertical_alignment="center")
        name.write(f"Research XP · referência {month_label(p)}")
        with button:
            download("Baixar", report, f"macro_research_xp_{p.key}.pdf", f"macro_{p.key}")


if page == "Macro":
    macro_page()


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


FILTERS = ["Todas", "Enviadas", "Prontas para revisão", "Gerar carta", "Pendentes"]


def letter_stage(row: dict) -> tuple[str, list[str]]:
    """Which filter a client falls in this month, and what is missing (to generate or to send)."""
    missing = []
    if not (crm.CLIENTS_DIR / row["slug"] / "risk_profile.pdf").exists():
        missing.append("suitability")
    if not pipeline.has_statement(row["slug"], MONTH):
        missing.append(f"extrato de {month_label(PERIOD)}")
    if not PERIOD.macro_report.exists():
        missing.append("macro research do mês")
    to_send = [label for value, label in [(row["cpf"], "CPF"), (row["email"], "e-mail")] if not value]
    if row["status"] == "sent":
        return "Enviadas", []
    ready = row["status"] in ("generated", "needs_review", "approved")
    missing = to_send if ready else missing + to_send        # a ready letter only lacks what sending needs
    if missing:
        return "Pendentes", missing
    return ("Prontas para revisão" if ready else "Gerar carta"), []


def generate_tab() -> None:
    stages = {r["slug"]: letter_stage(r) for r in rows}
    counts = {f: sum(1 for s, _ in stages.values() if f == "Todas" or s == f) for f in FILTERS}
    choice = st.segmented_control("Filtro", FILTERS, default="Todas", format_func=lambda f: f"{f} ({counts[f]})",
                                  label_visibility="collapsed", key="letters_filter") or "Todas"
    shown = [r for r in rows if choice == "Todas" or stages[r["slug"]][0] == choice]
    if not shown:
        st.info("Nenhum cliente nesse filtro.")
    else:
        table = st.dataframe(
            [{"Cliente": r["name"], "Conta": r["account"], "Perfil": PROFILE_PT.get(r["profile"], "—"),
              "Carta": f"{STATUS_ICON[r['status']]} {crm.STATUS_PT[r['status']]}",
              "O que falta": ", ".join(stages[r["slug"]][1]) or "—"} for r in shown],
            width="stretch", hide_index=True, on_select="rerun", selection_mode="multi-row",
            key=f"letters_table_{choice}")
        picked = [shown[i] for i in table.selection.rows]

        job = jobs()["current"]
        running = bool(job and not job["end"])
        can_generate = [r for r in (picked or shown) if stages[r["slug"]][0] in ("Gerar carta", "Prontas para revisão")
                        and r["status"] != "generating"]
        if choice in ("Gerar carta", "Todas", "Prontas para revisão"):
            label = (f"Gerar {len(can_generate)} carta(s) selecionada(s)" if picked
                     else f"Gerar {len([r for r in shown if stages[r['slug']][0] == 'Gerar carta'])} carta(s)")
            targets = can_generate if picked else [r for r in shown if stages[r["slug"]][0] == "Gerar carta"]
            if targets and st.button(label, type="primary", disabled=running):
                start_batch([r["slug"] for r in targets], MONTH, pipeline.BATCH_WORKERS)
                st.rerun()
            st.caption("Selecione linhas para gerar só esses clientes, ou para refazer uma carta já pronta.")
        if running:
            st.caption("As cartas estão sendo escritas no servidor. Pode trocar de página: o lote continua.")
        batch_progress()

        waiting = [r for r in (picked or shown) if f"extrato de {month_label(PERIOD)}" in stages[r["slug"]][1]]
        if choice == "Pendentes" and waiting:
            with st.expander(f"Anexar extrato de {month_label(PERIOD)}", expanded=bool(picked)):
                options = {r["name"]: r for r in waiting}
                row = options[st.selectbox("Cliente", list(options))]
                statement = st.file_uploader("Extrato XP do mês (PDF)", type="pdf", key="statement")
                if st.button("Ler extrato e calcular rentabilidade", type="primary", disabled=not statement):
                    with st.spinner("Lendo o extrato e buscando cotações (Yahoo, CVM, Banco Central)..."):
                        try:
                            info = pipeline.add_statement(row["slug"], statement.getvalue(), MONTH)
                            st.success(f"Rentabilidade no mês: {info['return_pct']:+.2f}%.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
        if choice == "Pendentes":
            st.caption("Suitability, CPF e e-mail: em Clientes > Editar. Macro research: na tela Macro.")


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
        st.caption(f"Checagens automáticas: números conferidos com os dados, sem promessa de retorno, pontos de "
                   f"atenção ligados a fatos da carteira. Custo: US$ {row['cost_usd'] or 0:.3f}.")

        with st.expander("Editar texto da carta"):
            letter = doc["letter"]
            with st.form("edit"):
                letter["opening_pt"] = st.text_area("Abertura", letter.get("opening_pt", ""))
                letter["performance_pt"] = [st.text_area(f"Desempenho no mês {i + 1}", p, height=140)
                                            for i, p in enumerate(letter.get("performance_pt", []))]
                if "consolidated_pt" in letter:
                    letter["consolidated_pt"] = st.text_area("Desempenho acumulado (12 meses)",
                                                             letter["consolidated_pt"], height=110)
                letter["macro_pt"] = st.text_area("Cenário econômico", letter.get("macro_pt", ""), height=120)
                letter["assessment_pt"] = st.text_area("Avaliação da carteira", letter.get("assessment_pt", ""),
                                                       height=120)
                for i, s in enumerate(letter.get("attention_points", [])):
                    s["text_pt"] = st.text_area(f"Ponto de atenção {i + 1}: {s.get('title_pt', '')}",
                                                s.get("text_pt", ""))
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
    head, pick = st.columns([3, 1], vertical_alignment="bottom")
    with head:
        title("Relatórios")
    options = {p.folder: p for p in periods.recent(count=24)}
    for folder in sorted({p.parent.name for p in crm.CLIENTS_DIR.glob("*/*/portfolio.pdf")}, reverse=True):
        options.setdefault(folder, periods.from_folder(folder))
    options = dict(sorted(options.items(), reverse=True))
    chosen = pick.selectbox("Mês de referência", list(options), index=list(options).index(MONTH),
                            format_func=lambda f: month_label(options[f]))
    if chosen != MONTH:
        st.session_state.folder = chosen
        st.query_params["m"] = chosen
        st.rerun()
    st.caption(f"Carta de {PERIOD.letter_date:%d/%m/%Y} · desempenho de {PERIOD.start:%d/%m/%Y} a {PERIOD.end:%d/%m/%Y}"
               f" · macro research {'anexado' if PERIOD.macro_report.exists() else 'pendente'}")
    generate, review = st.tabs(["Cartas do mês", "Revisar e enviar"])
    with generate:
        generate_tab()
    with review:
        review_tab()

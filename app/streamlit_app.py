"""Advisor platform: clients, letter generation (single or batch), review, approval and e-mail.

    streamlit run app/streamlit_app.py

On the server the OpenAI key, the SMTP credentials and APP_PASSWORD (access to the demo) come
from environment variables set as secrets; locally they come from .env.
"""

from __future__ import annotations

import json
import os
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
STATUS_ICON = {"pending": "⚪", "generating": "⏳", "generated": "🟢", "needs_review": "🟠", "approved": "✅", "sent": "📨", "error": "🔴"}

st.set_page_config(page_title="Carta Mensal XP · Assessor", page_icon="📈", layout="wide")
st.markdown("""
<style>
  [data-testid="stSidebar"] {background: #141414;}
  [data-testid="stSidebar"] * {color: #F2F2F2;}
  .xp-band {background:#141414; border-left:6px solid #FFC709; padding:14px 18px; border-radius:4px; margin-bottom:12px}
  .xp-band h2 {color:#fff; margin:0; font-size:1.35rem}
  .xp-band p {color:#cfcfcf; margin:2px 0 0 0; font-size:.9rem}
  div.stButton > button[kind="primary"] {background:#FFC709; color:#141414; border:0; font-weight:600}
</style>""", unsafe_allow_html=True)


def gate() -> None:
    """Optional password so a public demo link does not spend the OpenAI key or send e-mails freely."""
    expected = os.environ.get("APP_PASSWORD")
    if not expected or st.session_state.get("auth"):
        return
    st.markdown('<div class="xp-band"><h2>Carta Mensal XP</h2><p>Acesso do assessor</p></div>', unsafe_allow_html=True)
    typed = st.text_input("Senha de acesso", type="password")
    if typed:
        if typed == expected:
            st.session_state.auth = True
            st.rerun()
        st.error("Senha incorreta")
    st.stop()


@st.cache_resource
def boot() -> int:
    """Register the clients already in data/clients (the demo clients) once per server start."""
    crm.reset_interrupted()
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
        st.success("Lote concluído. Revise em **Revisão e envio**.")
        if not st.session_state.get(f"seen_{job['start']}"):
            st.session_state[f"seen_{job['start']}"] = True
            st.rerun(scope="app")


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


gate()
boot()
with st.sidebar:
    st.markdown("### 📈 Carta Mensal XP")
    st.caption(f"Referência: **{SETTINGS['period_end']:%m/%Y}** · carta de {SETTINGS['letter_date']:%d/%m/%Y}")
    page = st.radio("Menu", ["Clientes", "Gerar cartas", "Revisão e envio", "Como funciona"], label_visibility="collapsed")
    st.divider()
    st.caption("Rivet decide, Python executa: os números vêm de código e dados de mercado; "
               "a IA analisa e escreve; o assessor aprova antes de enviar.")

rows = crm.clients(MONTH)

# ------------------------------------------------------------------ Clientes
if page == "Clientes":
    st.markdown('<div class="xp-band"><h2>Clientes</h2><p>Carteira de clientes do assessor e status da carta do mês'
                '</p></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes", len(rows))
    c2.metric("Cartas geradas", sum(r["status"] not in ("pending", "error") for r in rows))
    c3.metric("Enviadas", sum(r["status"] == "sent" for r in rows))
    c4.metric("Custo de IA no mês", f"US$ {sum(r['cost_usd'] or 0 for r in rows):.2f}")

    st.dataframe(
        [{"Cliente": r["name"], "Conta": r["account"], "Perfil": PROFILE_PT.get(r["profile"], r["profile"]),
          "E-mail": r["email"] or "—", "CPF": "cadastrado" if r["cpf"] else "—",
          "Carta do mês": f"{STATUS_ICON[r['status']]} {crm.STATUS_PT[r['status']]}"} for r in rows],
        width="stretch", hide_index=True)

    with st.expander("➕ Adicionar cliente (extrato XP + perfil de investidor em PDF)"):
        with st.form("add"):
            statement = st.file_uploader("Extrato da carteira (PDF)", type="pdf")
            profile = st.file_uploader("Perfil de investidor / suitability (PDF)", type="pdf")
            email = st.text_input("E-mail do cliente")
            cpf = st.text_input("CPF (usado só como senha do PDF)")
            if st.form_submit_button("Cadastrar e calcular rentabilidade", type="primary"):
                if not (statement and profile):
                    st.error("Envie os dois PDFs.")
                else:
                    with st.spinner("Lendo o extrato e buscando cotações (Yahoo, CVM, Banco Central)..."):
                        try:
                            info = pipeline.add_client(statement.getvalue(), profile.getvalue(), email, cpf)
                            st.success(f"{info['name']} cadastrado ({info['profile']}). Rentabilidade no mês: "
                                       f"{info['return_pct']:+.2f}%. Leitura do extrato: "
                                       f"{'código' if info['reader'] == 'code' else 'IA (conferir)'}.")
                            for w in info["warnings"]:
                                st.caption(f"⚠️ {w}")
                        except Exception as exc:
                            st.error(f"Não foi possível cadastrar: {exc}")

    with st.expander("✏️ Atualizar e-mail e CPF"):
        if rows:
            names = {r["name"]: r for r in rows}
            chosen = names[st.selectbox("Cliente", list(names))]
            with st.form("contact"):
                email = st.text_input("E-mail", chosen["email"] or "")
                cpf = st.text_input("CPF", "", placeholder="cadastrado" if chosen["cpf"] else "")
                if st.form_submit_button("Salvar"):
                    crm.update_contact(chosen["slug"], email, cpf or chosen["cpf"] or "")
                    st.success("Salvo.")
                    st.rerun()

# ------------------------------------------------------------- Gerar cartas
elif page == "Gerar cartas":
    st.markdown('<div class="xp-band"><h2>Gerar cartas</h2><p>Um cliente ou o lote inteiro, em paralelo</p></div>',
                unsafe_allow_html=True)
    names = {f"{STATUS_ICON[r['status']]} {r['name']}": r["slug"] for r in rows}
    pending = [k for k, r in zip(names, rows) if r["status"] in ("pending", "error")]
    selected = st.multiselect("Clientes", list(names), default=pending or list(names))
    workers = st.slider("Cartas em paralelo", 1, 16, pipeline.BATCH_WORKERS,
                        help="Cada carta leva de 1 a 2 minutos esperando a IA; em paralelo, 20 cartas levam quase o "
                             "mesmo tempo que uma. O limite é a cota da OpenAI.")
    st.caption("No servidor, o lote do mês também roda sozinho no fechamento (python -m app.batch), e o assessor "
               "encontra as cartas na fila de revisão.")
    job = jobs()["current"]
    running = bool(job and not job["end"])
    if st.button(f"Gerar {len(selected)} carta(s)", type="primary", disabled=running or not selected):
        start_batch([names[k] for k in selected], workers)
        st.rerun()
    if running:
        st.caption("As cartas estão sendo escritas no servidor. Pode trocar de página: o lote continua.")
    batch_progress()

# ---------------------------------------------------------- Revisão e envio
elif page == "Revisão e envio":
    st.markdown('<div class="xp-band"><h2>Revisão e envio</h2><p>Nenhuma carta sai sem a aprovação do assessor</p>'
                '</div>', unsafe_allow_html=True)
    ready = [r for r in rows if r["status"] in ("generated", "needs_review", "approved", "sent")]
    if not ready:
        st.info("Nenhuma carta gerada ainda. Use **Gerar cartas**.")
        st.stop()
    labels = {f"{STATUS_ICON[r['status']]} {r['name']} · {crm.STATUS_PT[r['status']]}": r for r in ready}
    row = labels[st.selectbox("Carta", list(labels))]
    folder = pipeline.month_dir(row["slug"], MONTH)
    doc = letter_doc(row["slug"])

    left, right = st.columns([3, 2])
    with left:
        for image in pdf_pages(folder / "letter.pdf"):
            st.image(image, width="stretch")
    with right:
        st.download_button("⬇️ Baixar PDF", (folder / "letter.pdf").read_bytes(), f"carta_{row['slug']}_{MONTH}.pdf",
                           "application/pdf", width="stretch")
        notes = doc.get("advisor_notes", [])
        st.markdown(f"**Observações do revisor (IA):** {len(notes) or 'nenhuma'}")
        for n in notes:
            st.warning(f"**{n.get('rule', '')}** · “{n.get('quote', '')}”\n\n{n.get('problem', '')}\n\n"
                       f"*Sugestão:* {n.get('fix', '')}")
        st.caption(f"Checagens automáticas: números conferidos com os dados, sem promessa de retorno, sugestões "
                   f"dentro das regras. Custo: US$ {row['cost_usd'] or 0:.3f}.")

        with st.expander("✏️ Editar texto da carta"):
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
            if st.button("✅ Aprovar carta", type="primary", width="stretch"):
                crm.set_letter(row["slug"], MONTH, "approved")
                st.rerun()
        else:
            st.success(crm.STATUS_PT[row["status"]] + (f" para {row['sent_to']} em {row['sent_at']}"
                                                         if row["status"] == "sent" else ""))
        if row["status"] in ("approved", "sent"):
            to = st.text_input("Enviar para", row["email"] or "")
            if st.button("📨 Enviar por e-mail", width="stretch", disabled=not to):
                try:
                    with st.spinner("Protegendo o PDF com o CPF e enviando..."):
                        send_letter(folder, to, row["cpf"] or "", doc["letter"].get("subject_pt", "Sua carta mensal"),
                                    doc["client"]["first_name"], doc["client"].get("advisor_name") or "Seu assessor",
                                    SETTINGS.get("delivery", {}).get("pdf_password_cpf_digits", 6))
                    crm.mark_sent(row["slug"], MONTH, to)
                    st.success(f"Enviada para {to}. Senha do PDF: os primeiros dígitos do CPF.")
                except (MailError, OSError) as exc:
                    st.error(str(exc))

# ------------------------------------------------------------ Como funciona
else:
    st.markdown('<div class="xp-band"><h2>Como funciona</h2><p>Rivet decide, Python executa</p></div>',
                unsafe_allow_html=True)
    st.markdown("""
1. **Leitura do extrato** — o código lê o extrato padrão XP e confere todas as somas. Se o layout for
   desconhecido, um agente do Rivet extrai os dados e eles passam pelas mesmas conferências.
2. **Rentabilidade** — cotações diárias do Yahoo Finance (ações), cotas da CVM (fundos) e CDI/IPCA do
   Banco Central. Resultado por ativo, classe e carteira, contra CDI, Ibovespa e o benchmark do perfil.
3. **Fatos e sugestões candidatas** — regras objetivas (saldo parado, CDB vencido, concentração, falta
   de renda fixa, peso de renda variável) geram as sugestões possíveis para o perfil.
4. **Agente no Rivet** — o *Analista* resume o perfil, analisa o mês à luz do relatório macro da XP e
   escolhe 2 ou 3 sugestões; o *Redator* escreve a carta; o *Revisor* deixa observações para o assessor.
5. **Travas em código** — todo número da carta precisa existir nos dados; frases de promessa de retorno
   e sugestões fora das candidatas reprovam a versão, que é reescrita.
6. **PDF e envio** — carta de 2 páginas com gráficos; o assessor revisa, edita se quiser, aprova e
   envia por e-mail, com o PDF protegido pelo CPF do cliente.
""")
    st.caption("Código, prompts e grafo do Rivet em inglês; carta em português.")

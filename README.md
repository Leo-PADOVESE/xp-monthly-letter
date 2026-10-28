# XP Monthly Letter

Platform that lets an XP financial advisor generate, review and send a personalised
monthly portfolio letter to each client, one at a time or in batch. The letter is in
Portuguese, up to two pages, dated 07/05/2025, and delivered as a password-protected PDF.

Built for the Enter case. Code, prompts and the Rivet graph are in English.

**Design rule: Rivet decides, Python executes.** Python reads the statement, computes every
number and runs the checks; the Rivet graph only analyses and writes, from those numbers.

## How a letter is made

| Step | Where | What it does |
|---|---|---|
| 1. Read the statement | `core/ingestion.py` | XP statement PDF to structured JSON, with reconciliation checks. Unknown layouts fall back to the Rivet `portfolio_extraction` graph, whose output passes the same checks. |
| 2. Profitability | `core/profitability.py`, `core/market_data.py`, `core/fund_resolver.py` | Monthly return per asset, class and portfolio, vs CDI, Ibovespa and IPCA (Yahoo Finance, CVM, Banco Central). `core/history.py` rebuilds the last 12 months (or since the first investment) from the current positions, for the letter's main chart. |
| 3. Portfolio facts | `core/briefing.py` | Objective facts the letter may discuss (class weights, idle cash, matured bonds, concentration), plus every figure pre-formatted, including the return as % of the CDI and the contribution of each class. |
| 4. Letter | `core/letter_ai.py` + `rivet/` | Python writes `briefing.json` (client, profile document, statement, every result already formatted, the 12-month window, portfolio facts and the macro digest): the Rivet graph's only data input. Three agents read it: the Analyst (profile, performance and an assessment of the portfolio against the profile and the XP scenario, class by class, no buy/sell orders), the Writer and the Reviewer. Deterministic gates in Python: every figure must exist in the briefing, no promises of return, attention points anchored in portfolio facts, 300 to 600 words; the Reviewer's high findings on facts force a rewrite. Up to 2 rewrites. |
| 5. PDF and e-mail | `core/letter_pdf.py`, `core/mailer.py` | Two-page XP-styled PDF: portfolio vs CDI, Ibovespa, inflation and the profile benchmark, where the result came from by class, the class table with the XP view, and the per-asset monthly results. Sent by SMTP, protected with the first 6 CPF digits. |
| 6. Advisor platform | `app/`, `core/crm.py`, `core/pipeline.py` | Streamlit app: client CRM, batch generation in parallel, review, edit, approve and send. |

`docs/mvp_original/` keeps the output of the original Rivet MVP, for comparison.

## Run locally

Needs Python 3.12 and Node.js 20.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd rivet && npm install && cd ..
cp .env.example .env                                # then fill in the values
streamlit run app/streamlit_app.py
```

Batch from the command line: `python -m app.batch --all --workers 8`.

Single steps:

```bash
python -m core.ingestion data/clients/albert_da_silva/2025-05/portfolio.pdf
python -m core.profitability data/clients/albert_da_silva/2025-05 --source market
python -m core.letter_ai data/clients/albert_da_silva/2025-05
python -m core.letter_pdf data/clients/albert_da_silva/2025-05
```

After editing `rivet/prompts/*.md`, rebuild the graph with `node rivet/build_project.mjs`.

Tests run offline: `python -m pytest`.

## Deploy (Render)

`render.yaml` and the `Dockerfile` describe the service. On Render, create a Blueprint
from this repository and set the secrets `OPENAI_API_KEY`, `APP_PASSWORD` and, to send
e-mail, `SMTP_USER` and `SMTP_PASSWORD`. Keys live only in the server's secrets, never
in the repository.

## Data layout

```
data/
  macro_2025-02.pdf                  XP macro report, shared by all clients
  samples/*.yaml                     fictitious clients (scripts/make_sample_statement.py)
  clients/<client>/
    risk_profile.pdf                 suitability statement
    <YYYY-MM>/portfolio.pdf          monthly statement, plus the results and the letter
```

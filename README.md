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
| 2. Profitability | `core/profitability.py`, `core/market_data.py`, `core/fund_resolver.py` | Monthly return per asset, class and portfolio, vs CDI, Ibovespa and IPCA (Yahoo Finance, CVM, Banco Central). |
| 3. Suggestion candidates | `core/suggestions.py` | Rule-based list of what is worth discussing (idle cash, matured bonds, concentration, distance from the risk profile). No product names. |
| 4. Letter | `rivet/` + `core/letter_ai.py` | Analyst, Writer and Reviewer agents in Rivet. Deterministic gates in Python: every figure must exist in the data, no promises of return, suggestions only from the candidates, 300 to 600 words. Up to 2 rewrites; the Reviewer's remarks become notes for the advisor. |
| 5. PDF and e-mail | `core/letter_pdf.py`, `core/mailer.py` | Two-page XP-styled PDF; sent by SMTP, protected with the first 6 CPF digits. |
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

The service runs on the Starter plan with a persistent disk at `/var/data`. On start,
`scripts/entrypoint.sh` seeds the disk with the data shipped in the image (only files that are
missing) and links `data/` to it, so the CRM and the generated letters survive redeploys.

## Data layout

```
data/
  macro_2025-02.pdf                  XP macro report, shared by all clients
  samples/*.yaml                     fictitious clients (scripts/make_sample_statement.py)
  clients/<client>/
    risk_profile.pdf                 suitability statement
    <YYYY-MM>/portfolio.pdf          monthly statement, plus the results and the letter
```

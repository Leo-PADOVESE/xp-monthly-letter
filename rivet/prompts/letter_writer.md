## Task: write the monthly letter

Turn the analysis below into the client's monthly letter, in Brazilian Portuguese. It will be laid out on two A4 pages together with a chart of the consolidated portfolio against its benchmarks over the last 12 months (or since the first investment), a table of the portfolio by class with the XP view, and the per-asset results table, so the whole text must stay between 330 and 480 words. The letter has two clearly separate time frames: the reference month, and the consolidated window; every figure must say which one it belongs to.

Structure:
1. greeting with the client's first name;
2. opening: one sentence that tells, in plain words and without figures, how the month went and what drove it (e.g. "Abril foi um mês positivo para sua carteira, puxado principalmente pelas ações."). Never "apresentamos o desempenho" or similar;
3. performance of the month ("performance_pt", at most two paragraphs, under the heading "Desempenho no mês"): only figures of the reference month from "results" (never from "consolidated_window"), and say "no mês" or name the month at least once in each paragraph. First the month's consolidated result against the CDI, the profile benchmark and inflation, as differences in p.p. or side by side ("+3,95% no mês, contra +1,06% do CDI"); never as a percentage of the CDI. Then where the month's result came from, by asset class ("class_contribution"); then the most relevant movements by asset (best and worst performer, and the top contributor in reais when it is a different asset, explaining its larger weight), with losses stated plainly; the per-asset detail is in the table, so do not list every asset. Do not quote the 0,00% return of cash or of a matured bond, and never name a matured bond in this section: the worst performer is "highlights.worst_performer". An asset's return in the statement ("statement") is accumulated since the investment: for the month use "positions" and "highlights" only;
3b. consolidated performance ("consolidated_pt", one paragraph, under the heading "Desempenho acumulado", only when "consolidated_window" is given, otherwise empty): only figures of "consolidated_window", always with the window ("nos últimos 12 meses"): the portfolio's return and result in reais ("gain") against the CDI, the profile benchmark and the Ibovespa, saying it considers the current positions; then the result since the first investment ("since_purchase", with its date), explaining in plain words when it differs from the 12 months (older positions that are still below their purchase price). Never mix a month figure into this paragraph;
4. macro: the XP scenario in two or three sentences and what it means for the assets this client actually holds (name the classes or sectors, following the analyses). Quote each macro figure once;
5. assessment: the analysis' assessment_pt, tightened if needed, keeping its balance (what is well placed and what is exposed);
6. attention points: exactly the points in the analysis' assessment, same order, fact_id copied; keep them as topics to discuss with the advisor;
7. outlook ("O que esperar", two or three sentences, specific to this client): the one or two points of the XP scenario that matter most for the classes this client actually holds, named (e.g. "com a Selic alta no cenário da XP, os fundos de renda fixa e o CDB vencido seguem em foco; nas ações, o consumo interno é o ponto a acompanhar"), and what that means to watch in the coming months, conditional and attributed to XP, without figures already quoted and without promising returns. Never a generic sentence that would fit any client ("o cenário apresenta desafios", "a diversificação pode mitigar riscos");
8. closing (one or two sentences): invite the client to talk about the attention points of this letter, naming them briefly (e.g. "o valor do CDB vencido e o saldo parado em conta"), and the advisor's availability. No "melhores estratégias", no promise of results. No sign-off and no name: the PDF adds "Atenciosamente" and the advisor's signature.

Layout order (fixed by the PDF, mandatory): tiles, greeting, opening, month performance, consolidated performance with the chart, highlights, macro with the class table, assessment, attention points, the per-asset table of the month, and only then the outlook ("O que esperar"), the closing and the advisor's signature, right before the disclaimer. So the outlook and the closing are the last words of the letter: they must not refer to anything "abaixo" and must read as its ending.

Quote figures exactly as they appear in the analyses and attribute them only to what they measure (a class return is not the return of one fund type or one asset).

Wording rules (the letter goes to a real client and must follow suitability rules):
- Never state or imply that a movement will improve, increase or raise returns, gains or profitability ("pode melhorar a rentabilidade", "potencializar ganhos", "aumentar o retorno" are not allowed). Describe instead what a change does to the portfolio: diversifies, reduces concentration, adds liquidity, aligns the portfolio with the profile.
- The letter assesses; it does not recommend buying or selling specific assets.
- XP figures are projections: say "a XP projeta a Selic em 15,50% ao fim de 2025" (with the horizon from the digest), never "a Selic deve permanecer em". The outlook does not repeat them.
- Macro effects are conditional and attributed to XP: "o cenário projetado pela XP tende a favorecer...", never "vai render". Do not use the scenario to explain a movement that went the other way (a class that rose is not "explained" by an unfavorable view).
- A matured bond is money available to reinvest, not a bad result. Idle cash is "saldo parado sem rendimento"; you may quote its opportunity cost in reais, but not promise what it would earn.
- Each sentence says what it means grammatically. Address the client as "você" consistently and use correct Portuguese.
- When a class moved against the XP view in the month, write both facts in one sentence and how they fit ("as ações subiram no mês, mas a XP segue cautelosa com a bolsa brasileira, por isso vale acompanhar esse peso"). Do not qualify a weight ("significativa", "alta") unless a portfolio fact says so.
- Describe a class only with what the XP view and the portfolio facts support; do not attribute qualities such as "estabilidade", "proteção" or "potencial de retorno" that the inputs do not state.
- Never mention the "digest" or the analyses: the client reads "o cenário da XP" or "o relatório macro da XP". Never refer to the client by name or in the third person outside the greeting.
- The greeting appears only in greeting_pt. Each figure is quoted once in the whole letter. Do not compare a result with an expectation, a limit or an ideal that is not in the inputs.

If revision notes are given, fix every issue they list and keep the rest.

Return JSON with this schema:
{
  "subject_pt": "string (e-mail subject)",
  "greeting_pt": "string (e.g. Prezado Albert,)",
  "opening_pt": "string",
  "performance_pt": ["string (paragraphs, the month only)"],
  "consolidated_pt": "string (the 12-month window and since the first investment; empty if no consolidated_window)",
  "macro_pt": "string",
  "assessment_pt": "string",
  "attention_points": [{"fact_id": "string (copied)", "title_pt": "string", "text_pt": "string"}],
  "outlook_pt": "string",
  "closing_pt": "string"
}

### Briefing (client, results, portfolio facts and XP macro digest)
{{briefing}}

### Analysis (profile, performance and assessment, by the Analyst)
{{analysis}}

### Revision notes (empty on the first draft)
{{revision_notes}}

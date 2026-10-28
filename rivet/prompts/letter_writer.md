## Task: write the monthly letter

Turn the analysis below into the client's monthly letter, in Brazilian Portuguese. It will be laid out on two A4 pages together with a chart of the consolidated portfolio against its benchmarks over the last 12 months (or since the first investment), a table of the portfolio by class with the XP view, and the per-asset results table, so the whole text must stay between 330 and 480 words.

Structure:
1. greeting with the client's first name;
2. opening: one sentence that tells, in plain words and without figures, how the month went and what drove it (e.g. "Abril foi um mês positivo para sua carteira, puxado principalmente pelas ações."). Never "apresentamos o desempenho" or similar;
3. performance (at most two paragraphs): the month's consolidated result first, against the CDI (as a % of the CDI when it applies: "o equivalente a 374% do CDI", never "superou o CDI em 374%"), the profile benchmark and inflation; then, when "consolidated_window" is given, one sentence on the portfolio over that window against the CDI and the Ibovespa, saying it considers the current positions; then where the month's result came from, by asset class ("class_contribution"); then the most relevant movements by asset (best and worst performer, and the top contributor in reais when it is a different asset, explaining its larger weight), with losses stated plainly; the per-asset detail is in the table, so do not list every asset. Do not quote the 0,00% return of cash or of a matured bond;
4. macro: the XP scenario in two or three sentences and what it means for the assets this client actually holds (name the classes or sectors, following the analyses). Quote each macro figure once;
5. assessment: the analysis' assessment_pt, tightened if needed, keeping its balance (what is well placed and what is exposed);
6. attention points: exactly the points in the analysis' assessment, same order, fact_id copied; keep them as topics to discuss with the advisor;
7. outlook: what to watch, without promising returns;
8. closing: availability of the advisor for a conversation.

Quote figures exactly as they appear in the analyses and attribute them only to what they measure (a class return is not the return of one fund type or one asset).

Wording rules (the letter goes to a real client and must follow suitability rules):
- Never state or imply that a movement will improve, increase or raise returns, gains or profitability ("pode melhorar a rentabilidade", "potencializar ganhos", "aumentar o retorno" are not allowed). Describe instead what a change does to the portfolio: diversifies, reduces concentration, adds liquidity, aligns the portfolio with the profile.
- The letter assesses; it does not recommend buying or selling specific assets.
- XP figures are projections: say "a XP projeta a Selic em 15,50% ao fim de 2025" (with the horizon from the digest), never "a Selic deve permanecer em". The outlook does not repeat them.
- Macro effects are conditional and attributed to XP: "o cenário projetado pela XP tende a favorecer...", never "vai render". Do not use the scenario to explain a movement that went the other way (a class that rose is not "explained" by an unfavorable view).
- A matured bond is money available to reinvest, not a bad result. Idle cash is "saldo parado sem rendimento"; you may quote its opportunity cost in reais, but not promise what it would earn.
- Each sentence says what it means grammatically. Address the client as "você" consistently and use correct Portuguese.
- Describe a class only with what the XP view and the portfolio facts support; do not attribute qualities such as "estabilidade", "proteção" or "potencial de retorno" that the inputs do not state.
- Never mention the "digest" or the analyses: the client reads "o cenário da XP" or "o relatório macro da XP". Never refer to the client by name or in the third person outside the greeting.
- The greeting appears only in greeting_pt. Each figure is quoted once in the whole letter. Do not compare a result with an expectation, a limit or an ideal that is not in the inputs.

If revision notes are given, fix every issue they list and keep the rest.

Return JSON with this schema:
{
  "subject_pt": "string (e-mail subject)",
  "greeting_pt": "string (e.g. Prezado Albert,)",
  "opening_pt": "string",
  "performance_pt": ["string (paragraphs)"],
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

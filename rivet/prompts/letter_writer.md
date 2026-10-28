## Task: write the monthly letter

Integrate the analyses below into the client's monthly letter, in Brazilian Portuguese. It will be laid out on two A4 pages together with two charts and a small results table, so the whole text must stay between 380 and 520 words.

Structure:
1. greeting with the client's first name;
2. opening: one or two sentences with the month and the purpose of the letter;
3. performance: the month's result versus CDI and the profile benchmark; the most impactful movements, with losses stated plainly and, when the analysis links them to the XP scenario, that possible explanation; the best performer and the worst performer (by return); the top contributor in reais when it is a different asset from the best performer, explaining that its weight in the portfolio is larger; then the attention points;
4. macro: how the XP scenario may affect the portfolio;
5. suggestions: exactly the movements in "Suggestions", same order, candidate_id and type copied; each text starts with "Discutir com o assessor a possibilidade de..." (or a close variation) and never states where the money must go, nor names a product or ticker the suggestion does not name;
6. outlook: what to expect, without promising returns;
7. closing: availability of the advisor for a conversation.

Choose the two charts that best support the story, from: "allocation" (portfolio by asset class), "contribution" (contribution of each asset in R$), "benchmarks" (portfolio vs CDI, Ibovespa and profile benchmark).

Quote figures exactly as they appear in the analyses and attribute them only to what they measure (a class return is not the return of one fund type or one asset).

Wording rules (the letter goes to a real client and must follow suitability rules):
- Never state or imply that a movement will improve, increase or raise returns, gains or profitability ("pode melhorar a rentabilidade", "potencializar ganhos", "aumentar o retorno" are not allowed). Describe instead what the movement does to the portfolio: diversifies, reduces concentration, adds liquidity, aligns the portfolio with the profile, puts idle money to work at the CDI rate.
- XP figures are projections: say "a XP projeta a Selic em 15,50% ao fim de 2025" (with the horizon from the digest), never "a Selic deve permanecer em". Quote each macro figure once, in the macro section; the outlook does not repeat them.
- Each sentence says what it means grammatically: "incluir renda fixa pode trazer proteção", not "a carteira não possui renda fixa, o que pode oferecer proteção".
- Macro effects are conditional and attributed to XP: "o cenário projetado pela XP tende a favorecer...", never "vai render".
- A matured bond is money available to reinvest, not a bad result: do not describe it as "sem retorno" or as a concern.
- Idle cash is "saldo parado sem rendimento"; you may quote its opportunity cost in reais, but not promise what it would earn.
- Address the client as "você" consistently; use correct Portuguese ("custo de oportunidade", "ajudá-lo"), and avoid starting sentences with "Apesar de" unless a contrast follows in the same sentence.

Each suggestion text keeps the portfolio fact it rests on (e.g. "sua carteira não tem renda fixa"), and its title says no more than its text. Do not compare a result with an expectation, a limit or an ideal that is not in the inputs (no "abaixo do esperado", "acima do limite ideal"; the concentration fact gives the 15% reference).

The greeting appears only in greeting_pt. performance_pt has at most two paragraphs and each figure is quoted once in the whole letter.

If revision notes are given, fix every issue they list and keep the rest, including every suggestion that is grounded in a portfolio fact.

Return JSON with this schema:
{
  "subject_pt": "string (e-mail subject)",
  "greeting_pt": "string (e.g. Prezado Albert,)",
  "opening_pt": "string",
  "performance_pt": ["string (paragraphs)"],
  "macro_pt": "string",
  "suggestions_intro_pt": "string",
  "suggestions": [{"candidate_id": "string (copied)", "type": "opportunity|protection (copied)", "title_pt": "string", "text_pt": "string"}],
  "outlook_pt": "string",
  "closing_pt": "string",
  "charts": ["allocation|contribution|benchmarks", "allocation|contribution|benchmarks"]
}

### Client
{{client}}

### Client profile
{{profile_summary}}

### Portfolio performance analysis
{{performance_analysis}}

### XP macro digest
{{macro_digest}}

### Suggestions
{{recommendations}}

### Revision notes (empty on the first draft)
{{revision_notes}}

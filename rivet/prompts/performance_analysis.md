## Task: analyze the portfolio's performance in the month

You receive the portfolio, the profitability results already calculated by our engine and the XP macro digest. Your job is to choose what matters and explain it, never to recalculate.

Explain:
- the headline: the consolidated portfolio return versus CDI (and as a % of the CDI, when "return_as_pct_of_cdi" applies), versus the profile benchmark and versus inflation (real return);
- where the result came from by asset class ("class_contribution", in reais and p.p.);
- when "consolidated_window" is given: the portfolio over that window (12 months or since the first investment) against the CDI, the Ibovespa, inflation and the profile benchmark, and the result since purchase; it is rebuilt from the current positions, so say "considerando as posições atuais";
- which asset rose the most and which fell the most (by return %), and which asset contributed the most and the least in reais. Mention when they are different assets and why (weight);
- how each asset class and each fund type behaved, with the right sign: say which were positive and which negative;
- the assets that hurt the most in reais (bottom contributors), not only the worst return;
- the most impactful movements in reais, and losses stated plainly (asset, return and how much it took from the portfolio in reais);
- for each relevant loss or gain, a possible explanation from the XP macro digest only when the digest supports it (e.g. a sector or asset class it mentions); if the digest says nothing about it, do not make up a cause;
- points of attention from the data (for example idle cash and its opportunity cost, a matured bond, data caveats such as a proxy used for a fund). A matured bond shows +0,00% because it already paid out: describe it as an amount available to reinvest, never as "sem retorno" or a loss. Do not quote the 0,00% return of cash or of a matured bond as a class result.

Use the figures exactly as written in the results. Attribute each figure only to what it measures:
- "classes" are whole asset classes (stocks, fixed income, cash); funds are reported only by type in "fund_types", so name the type ("fundos multimercado") with its own return; for one asset, use "positions".
- Never present the return of a class as the return of a subset of it, or the other way around. "Renda fixa (CDB)" is only the CDBs held directly; fixed income funds are a fund type.
- A contribution in reais comes from weight and return together; say "weight" only when the asset's weight is clearly larger than the best performer's.
- "highlights" already ranks the assets: best and worst performer by return, top and bottom contributor in reais.

Return JSON with this schema:
{
  "headline_pt": "string (one sentence)",
  "attribution_pt": "string (one sentence: which classes produced the result)",
  "window_pt": "string (one sentence on the consolidated window, or empty if not given)",
  "best_performer": {"asset": "string", "return": "string"},
  "worst_performer": {"asset": "string", "return": "string"},
  "top_contributor": {"asset": "string", "contribution": "string"},
  "bottom_contributor": {"asset": "string", "contribution": "string"},
  "class_comments_pt": [{"asset_class": "string", "comment": "string"}],
  "attention_points_pt": ["string"],
  "macro_links_pt": ["string (movement + the macro point that may explain it)"],
  "paragraph_pt": "string (one paragraph in pt-BR, max 120 words, for the letter)"
}

### Client
{{client}}

### Portfolio (statement)
{{portfolio_text}}

### XP macro digest
{{macro_digest}}

### Profitability results (calculated by our engine; figures in "formatted" are the ones to quote)
{{profitability}}

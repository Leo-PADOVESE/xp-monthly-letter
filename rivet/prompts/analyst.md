## Task: analyze the client's month, in three parts

The briefing below was prepared by our Python engine: the client, the risk profile document, the statement, every result already calculated and formatted, the portfolio facts and the XP macro digest. Your job is to choose what matters and explain it, never to recalculate. You do not recommend buying or selling assets.

### Part 1: profile
From the risk profile document ("profile"), what the letter must respect: horizon, tolerance to volatility, objectives, compatible products and explicit restrictions (e.g. dividend-paying companies only).

### Part 2: performance (from "results")
- Two time frames, never mixed: everything in "results" is the reference month only, except "consolidated_window" (the 12-month window, or since the first investment). The statement's per-asset "rentabilidade" is accumulated since each investment, not the month: for the month use "positions" and "highlights".
- The headline: the month's return versus the CDI, the profile benchmark and inflation (real return), as differences in p.p. or side by side; never as a percentage of the CDI.
- Where the result came from by asset class ("class_contribution", in reais and p.p.).
- When "consolidated_window" is given, in "window_pt" and only there: the portfolio over that window against the CDI, the Ibovespa, inflation and the profile benchmark, and the result since the first investment ("since_purchase", with its date), with why the two differ when they do. It is rebuilt from the current positions: say "considerando as posições atuais".
- The best and worst performer by return and the top and bottom contributor in reais ("highlights"). A contribution comes from weight and return together: mention weight only when the asset's weight in "positions" is clearly larger than the best performer's.
- Losses stated plainly (asset, return, reais). A possible explanation from the XP digest only when the digest supports it; never "explain" a class by a scenario that points the other way.
- Points of attention from the data: idle cash and its opportunity cost, a matured bond (+0,00% because it already paid out: an amount available to reinvest, never "sem retorno"), a fund priced by proxy. Never quote the 0,00% of cash or of a matured bond as a class result.
- Attribution: "classes" are whole classes; funds appear only by type in "fund_types"; one asset is in "positions". Never present the return of a class as the return of a subset of it, or the other way around. "Renda fixa (CDB)" is only the CDBs held directly.

### Part 3: assessment (portfolio vs profile and XP scenario)
- Class by class, using the classes and weights in the "class_weights" portfolio fact (copied exactly). The XP view comes from the digest's asset_class_implications ("favorable", "neutral" or "unfavorable"); when the digest says nothing about a class, or for "Saldo em conta", use "neutral".
- "profile_fit_pt": one short sentence on what the class does for this client in this scenario (protection, liquidity, growth, inflation defence, concentration risk), consistent with the XP view: do not call a class "estável" or "proteção" when the digest sees it as volatile or uncertain, and never mention "potencial de retorno".
- When a class moved against the XP view in the month (e.g. stocks rose while the XP view on Brazilian equities is unfavorable), say so explicitly and keep both facts: one month's result does not change the scenario, and the scenario is why the class deserves attention. Never leave the two side by side unexplained.
- A class made only of matured bonds is "vencido, disponível para reinvestir": no XP view on its return ("neutral").
- Do not qualify a weight ("exposição significativa", "alta concentração") unless a portfolio fact says so; quote the weight instead.
- "assessment_pt": is the mix coherent with the profile given the scenario? Name the one or two classes that matter most for this client, and the sectors the digest flags when the client holds stocks in them. Balanced: what is well placed and what is exposed.
- "attention_points": 1 to 3 objective facts worth a conversation, each citing the id of a portfolio fact. Phrase each as a topic to discuss ("vale conversar com seu assessor sobre..."), never as an order; never say where the money must go or name a product; describe what a change would do (diversify, reduce concentration, add liquidity, align with the profile), never that it would improve returns.
- XP figures are projections with a horizon ("a XP projeta a Selic em 15,50% ao fim de 2025").

Client-facing strings are in Brazilian Portuguese, address the client as "você", never by name or in the third person, and never mention the "digest" (it is "o cenário da XP"). Copy figures exactly as written in the briefing. If revision notes are given, fix what they say.

Return JSON with this schema:
{
  "profile": {"profile_pt": "string", "horizon": "string", "volatility_tolerance": "string",
              "objectives": ["string"], "restrictions": ["string"], "summary_pt": "string (max 40 words)"},
  "performance": {
    "headline_pt": "string", "attribution_pt": "string", "window_pt": "string (empty if no consolidated_window)",
    "movers_pt": "string (best/worst performer, top contributor and losses)",
    "attention_points_pt": ["string"], "macro_links_pt": ["string (movement + the XP point that may explain it)"]
  },
  "assessment": {
    "class_views": [{"asset_class": "string (copied)", "weight": "string (copied)",
                     "xp_view": "favorable|neutral|unfavorable", "profile_fit_pt": "string (max 18 words)"}],
    "assessment_pt": "string (max 90 words)",
    "attention_points": [{"fact_id": "string", "title_pt": "string (max 7 words)", "text_pt": "string (max 45 words)"}],
    "outlook_pt": "string (max 60 words: what to watch for the classes this client holds, named, from the XP scenario; no macro figures, no promise of returns, nothing generic)"
  }
}

### Briefing
{{briefing}}

### Revision notes (empty on the first draft)
{{revision_notes}}

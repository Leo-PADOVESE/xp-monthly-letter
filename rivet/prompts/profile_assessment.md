## Task: assess how the portfolio sits in the XP scenario, for this client's profile

You do not recommend buying or selling assets. You assess: given the client's risk profile and the XP macro digest, how is the current portfolio positioned for the coming months? Where is it well placed, where is it exposed, and what is worth discussing with the advisor?

Rules:
- Work class by class, using the classes and weights in the "class_weights" portfolio fact (copy each class name and weight exactly as written). For each class, take the XP view from the digest's asset_class_implications ("favorable", "neutral" or "unfavorable"); if the digest says nothing about that class, use "neutral" and say so. "Saldo em conta" has no XP view: use "neutral".
- "profile_fit_pt" reads that class for this client in one short sentence: what the class does for a client with this profile in this scenario (protection, liquidity, growth, inflation defence, concentration risk), linking to the profile's horizon, tolerance or restrictions when relevant.
- "assessment_pt" is the overall reading: is the mix coherent with the profile given the scenario? Name the one or two classes that matter most for this client (by weight or by exposure to the scenario) and the sectors the digest flags when the client holds stocks in them. Be balanced: say what is well placed as well as what is exposed.
- "attention_points" are 1 to 3 objective facts worth a conversation, each citing the id of a portfolio fact (idle cash, matured bond, concentration, no fixed income, a class the digest sees as unfavorable that weighs a lot). Phrase each as a topic to discuss ("vale conversar com seu assessor sobre..."), never as an order, and never say where the money must go or name a product.
- Describe what a change would do to the portfolio (diversify, reduce concentration, add liquidity, align with the profile), never that it would improve or increase returns.
- XP figures are projections with a horizon ("a XP projeta a Selic em 15,50% ao fim de 2025"), never current values.
- If revision notes are given, fix what they say about the assessment.

Return JSON with this schema:
{
  "class_views": [
    {"asset_class": "string (copied from class_weights)", "weight": "string (copied)",
     "xp_view": "favorable|neutral|unfavorable", "profile_fit_pt": "string (pt-BR, max 18 words)"}
  ],
  "assessment_pt": "string (one paragraph in pt-BR, max 90 words)",
  "attention_points": [
    {"fact_id": "string (id of a portfolio fact)", "title_pt": "string (max 7 words)", "text_pt": "string (pt-BR, max 45 words)"}
  ],
  "outlook_pt": "string (one paragraph in pt-BR, max 60 words: what to watch in the coming months, without repeating the macro figures and without promising returns)"
}

### Client profile
{{profile_summary}}

### XP macro digest
{{macro_digest}}

### Portfolio performance analysis
{{performance_analysis}}

### Portfolio facts (calculated by our engine)
{{portfolio_facts}}

### Revision notes (empty on the first draft)
{{revision_notes}}

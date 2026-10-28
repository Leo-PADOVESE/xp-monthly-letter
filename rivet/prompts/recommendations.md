## Task: suggest portfolio movements for the coming month

Our rules engine has already listed the movements that are objectively justified for this client ("candidates"), each with its type and its basis in the portfolio. Your job is to choose and explain, not to invent movements.

Rules:
- Choose 2 or 3 candidates. Prefer, in this order: a matured bond or idle cash to put to work, a protection need (no fixed income, concentration, a heavy class that fell), and at most one macro opportunity.
- Use a macro candidate only if the XP macro digest is favorable or neutral for that asset class, and say which projection supports it.
- Do not change the action of a candidate and do not name products or tickers that the candidate does not name. Never state where the money must go: every action is a possibility to discuss with the advisor ("discutir com o assessor a possibilidade de...").
- Do not choose two candidates that point to the same instrument for the same money.
- The rationale links three things: the candidate's basis (fact), the client's profile and the XP scenario. Explain what the movement does to the portfolio (diversifies, reduces concentration, gives liquidity, puts idle money to work at the CDI rate), never that it will improve or increase returns.
- XP figures are projections with a horizon (e.g. "a XP projeta a Selic em 15,50% em 2025"), never current values.
- If revision notes are given, fix what they say about the suggestions.

Return JSON with this schema:
{
  "suggestions": [
    {
      "candidate_id": "string (id from the candidates)",
      "type": "opportunity|protection (copied from the candidate)",
      "title_pt": "string (max 8 words)",
      "action_pt": "string (the candidate's action, one sentence)",
      "rationale_pt": "string (fact + profile + XP scenario, max 60 words)"
    }
  ],
  "outlook_pt": "string (one paragraph in pt-BR, max 70 words: what to watch in the coming months given the scenario, without repeating the macro figures and without promising returns)"
}

### Candidates (from our rules engine)
{{suggestion_candidates}}

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

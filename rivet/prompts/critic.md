## Task: review the letter before it goes to the advisor

Every figure in the letter is already verified automatically against the source data, so do NOT check numbers or word count. Review only what needs judgement. The letter will be sent to a real client.

The suggestions were chosen from candidates produced by our rules engine, which already checks suitability and grounding; do not judge whether a suggestion fits the profile.

Check:
- "fatos": every statement about the portfolio agrees with the profitability results and the portfolio facts: which asset, class or fund type was positive or negative, best or worst, concentrated or matured; claims such as "bom desempenho" or "proteção contra a inflação" are supported; XP figures are presented as projections, not current values. A wrong statement is high. (Formatting of figures is checked elsewhere; check meaning only.)
- "coerência": no two passages contradict each other, and no suggestion contradicts another. High.
- "nomes": correct client name, reference month and advisor; the letter speaks to the client as "você" (not in the third person). High.
- "linguagem": Brazilian Portuguese, formal and clear tone; no repeated ideas or figures between sections. Medium or low.
- "promessa": wording that implies improved or guaranteed returns. An automatic check already blocks the obvious cases, so report it as medium at most, as a note for the advisor.

Report an issue only when you can quote the exact passage that breaks one of the rules above. Severity "high" means the letter must not be sent as it is; use "low" for style preferences. Do not report something that is correct.

Return JSON with this schema:
{
  "approved": true,
  "issues": [{"severity": "high|medium|low", "rule": "fatos|coerência|nomes|linguagem|promessa", "quote": "exact passage from the letter", "problem": "string", "fix": "string"}]
}
Write "problem" and "fix" in Brazilian Portuguese, for the advisor. Set "approved" to false only if there is a high issue.

### Client
{{client}}

### Client profile
{{profile_summary}}

### Profitability results
{{profitability}}

### Portfolio facts
{{portfolio_facts}}

### XP macro digest
{{macro_digest}}

### Draft letter
{{letter}}

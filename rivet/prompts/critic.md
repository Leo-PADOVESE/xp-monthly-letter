## Task: review the letter before it goes to the advisor

Every figure in the letter is already verified automatically against the source data, so do NOT check numbers or word count. Review only what needs judgement. The letter will be sent to a real client.

The letter assesses the portfolio against the client's profile and the XP scenario; it does not recommend buying or selling. Each attention point is anchored in a portfolio fact checked by code.

Time frames: every figure in "results" is for the reference month only, except "consolidated_window" (the 12-month window and the result since the first investment). The statement's per-asset "rentabilidade" is accumulated since each investment, not the month, so never use it to judge a month figure: the month's return of each asset is in "results.positions". "performance_pt" is about the month and "consolidated_pt" about the window.

Check:
- "período": a figure presented in the wrong time frame (a 12-month figure called the month's, or the other way round). High.
- "fatos": every statement about the portfolio agrees with the profitability results and the portfolio facts: which asset, class or fund type was positive or negative, best or worst, concentrated or matured; claims such as "bom desempenho" or "proteção contra a inflação" are supported; XP figures are presented as projections, not current values. A wrong statement is high. (Formatting of figures is checked elsewhere; check meaning only.)
- "coerência": no two passages contradict each other (e.g. the scenario "explaining" a class that went the other way). High.
- "nomes": correct client name, reference month and advisor; the letter speaks to the client as "você" (not in the third person). High.
- "estrutura": the letter ends with the outlook ("O que esperar"), the closing and the advisor's signature, placed after the per-asset table and right before the disclaimer (the PDF lays them out in that order). An outlook or closing that does not work as the ending, refers to content below it, or a sign-off or farewell inside another section, is medium. An outlook that does not name the client's own classes or assets, or a closing that does not mention the attention points (generic text that would fit any client), is high.
- "linguagem": Brazilian Portuguese, formal and clear tone; no repeated ideas or figures between sections. Medium or low.
- "promessa": wording that implies improved or guaranteed returns. An automatic check already blocks the obvious cases, so report it as medium at most, as a note for the advisor.

Not issues: explaining the top contributor in reais by its larger weight when "positions" shows a larger weight than the best performer's; a matured CDB at +0,00% does not make statements about fixed income funds wrong; describing a class as the XP digest does; leaving a portfolio fact out of the attention points (there are at most 3, chosen by the Analyst); a 12-month result different from the result since the first investment (they measure different periods); saying that a class rose in the month despite an unfavorable XP view (that contrast is required, it is not a contradiction).

Report an issue only when you can quote the exact passage that breaks one of the rules above. Severity "high" means the letter must not be sent as it is; use "low" for style preferences. Do not report something that is correct.

Return JSON with this schema:
{
  "approved": true,
  "issues": [{"severity": "high|medium|low", "rule": "fatos|período|coerência|nomes|estrutura|linguagem|promessa", "quote": "exact passage from the letter", "problem": "string", "fix": "string"}]
}
Write "problem" and "fix" in Brazilian Portuguese, for the advisor. Set "approved" to false only if there is a high issue.

### Briefing (client, profile document, results, portfolio facts and XP macro digest)
{{briefing}}

### Draft letter
{{letter}}

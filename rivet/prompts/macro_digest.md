## Task: digest the XP macro research for this month's client letters

This digest is produced once per month and reused for every client, so keep it factual and client-agnostic.

Extract from the report below:
- the report date and title;
- the key projections (Selic, IPCA, GDP, exchange rate, fiscal), with the numbers copied exactly as written in the report;
- the main risks and the overall market sentiment;
- the implications for each asset class (post-fixed income, inflation-linked bonds, credit, multimarket funds, Brazilian equities, international), as stated or clearly implied by the report;
- which equity sectors the report sees as more exposed or more resilient.

Return JSON with this schema:
{
  "report_date": "string",
  "report_title": "string",
  "projections": [{"indicator": "string", "value": "string", "horizon": "string"}],
  "sentiment": "string (one sentence)",
  "risks": ["string"],
  "asset_class_implications": [{"asset_class": "string", "view": "favorable|neutral|unfavorable", "why": "string"}],
  "sector_notes": ["string"],
  "summary_pt": "string (one paragraph in pt-BR, max 90 words, for the client letter)"
}

### Letter date
{{letter_date}}

### XP macro research (raw text)
{{macro_text}}

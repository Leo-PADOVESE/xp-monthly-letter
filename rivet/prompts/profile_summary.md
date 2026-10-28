## Task: summarize the client's investor profile (suitability)

Read the client's risk profile document and extract what the letter and the suggestions must respect.

Return JSON with this schema:
{
  "profile": "conservative|moderate|aggressive",
  "profile_pt": "string (e.g. Moderado)",
  "horizon": "string",
  "volatility_tolerance": "string",
  "objectives": ["string"],
  "compatible_products": ["string"],
  "restrictions": ["string (explicit rules from the document, e.g. dividend-paying companies only)"],
  "summary_pt": "string (one sentence in pt-BR, max 40 words)"
}

### Risk profile classification computed from the document
{{profile_label}}

### Risk profile document
{{risk_profile_text}}

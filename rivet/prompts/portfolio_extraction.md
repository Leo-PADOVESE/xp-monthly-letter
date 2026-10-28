## Task: extract the positions of an investment statement (fallback reader)

Our code reader could not recognise this statement. Extract its data so it can be validated by our checks (the sum of the positions must match the total invested, and invested + cash must match the total equity).

Copy every number exactly as printed. Do not skip any position. If a field is not in the statement, use null.

Return JSON with this schema:
{
  "client_name": "string",
  "account": "string|null",
  "snapshot_date": "dd/mm/yyyy|null",
  "advisor_code": "string|null",
  "advisor_name": "string|null",
  "total_equity": "string",
  "total_invested": "string",
  "cash_available": "string",
  "positions": [
    {
      "section": "string (section title as printed)",
      "name": "string",
      "market_value": "string",
      "allocation_pct": "string|null",
      "cumulative_return_pct": "string|null",
      "quantity": "string|null",
      "average_price": "string|null",
      "last_price": "string|null",
      "invested_amount": "string|null",
      "rate": "string|null",
      "maturity_date": "string|null"
    }
  ]
}

### Statement text
{{statement_text}}

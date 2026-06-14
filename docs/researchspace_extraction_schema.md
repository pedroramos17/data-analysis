# ResearchSpace Extraction Schema

ResearchSpace stores methodology extraction output in `QuantExtraction`.

Expected JSON shape:

```json
{
  "methodology": ["walk-forward validation"],
  "datasets": ["daily equity bars"],
  "models": ["baseline regression"],
  "validation": ["purged split"],
  "factors": [
    {
      "name": "RegimeSpread",
      "expression_json": {"kind": "operand", "name": "regime_spread"},
      "rationale": "Supported by cited methodology.",
      "support_status": "PARTIAL"
    }
  ],
  "support_status": "PARTIAL"
}
```

Partial JSON is accepted and converted to a stable shape with empty lists where
sections are missing. Unknown support status values become `NEEDS_REVIEW`.

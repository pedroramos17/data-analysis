# QuantSpace Codex Prompt Export

Codex prompt export turns a `FactorCandidate` into an implementation prompt for
Sourceflow.

The prompt includes:

- Candidate name.
- Candidate status.
- Support status.
- Symbolic expression JSON.
- Research-only implementation rules.

The prompt excludes profitability claims and preserves `NEEDS_BACKTEST`
framing. Prompt export is controlled by `QUANTSPACE_CODEX_PROMPT_EXPORT`.

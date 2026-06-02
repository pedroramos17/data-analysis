# Quant4 Multifractal Reporting

Reports are Markdown-first and include dataset ID, config, method, q grid,
scale range, warnings, diagnostics, risk, regime, portfolio notes, and
interpretation cautions.

Plot generation uses matplotlib when available. If matplotlib is missing, the
plot writer creates an explicit placeholder artifact instead of silently
pretending plots were produced.

All reporting outputs are research diagnostics only. They are not predictions,
validity claims, investment advice, or trading signals.

# Quant4 Multifractal Methods Phase 5

Phase 5 adds local-first method coverage beyond MF-DFA:

- MF-DMA in backward, centered, and forward moving-average modes.
- MF-DCCA / MF-X-DFA for aligned two-series cross-scaling diagnostics.
- A partition-function baseline for strictly positive measures such as volume,
  volatility, liquidity, or inter-event durations.
- A wavelet diagnostics interface with optional PyWavelets CWT support and a
  pure-Python Ricker fallback.

These methods are research diagnostics only. They do not validate factor
profitability, trading suitability, causality, or live execution readiness.

## Limitations

The partition-function module is a baseline over positive box masses. It is
useful for comparing scale behavior across measures, but it is not a full
wavelet-leader or measure-theoretic multifractal formalism.

The wavelet module reports scale energy diagnostics. When PyWavelets is not
installed, Quant4 uses a deterministic Ricker fallback so local tests and CPU
workflows still run. The fallback is not a wavelet-leader spectrum and should
not be interpreted as a replacement for full leader-based multifractal analysis.

MF-DCCA assumes the two input series are already aligned and available at the
same timestamps. Callers must construct those aligned, no-lookahead windows
before invoking the method.

# Quant4 Multifractal LOB Readiness

LOB support lives under `quant4/services/multifractal/lob/`. It is an
interface layer for later venue-specific depth data and should remain optional.

Current capabilities:

- synthetic LOB-like snapshots for tests
- spread, imbalance, event-duration, and inter-event-duration feature helpers
- MF-DFA on spread and imbalance series
- partition-style diagnostics for positive duration measures
- MF-DCCA between buy-side and sell-side features where aligned data exists

Forex LOB depth remains venue-dependent and optional. Equities, futures, and
crypto feeds can be normalized if local data is supplied by the caller. Tests
use synthetic data and do not require hidden network access.

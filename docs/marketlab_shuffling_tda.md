# MarketLab Shuffling And TDA

MarketLab provides lightweight shuffle and topology validation fallbacks that
run without heavy optional dependencies.

Initial shufflers:

- `GeneralizedTimeWindowShuffle`
- `TemporalPatchShuffle`
- `OverlapWindowShuffle`
- `IMFShuffle`
- `TopologyAwareShuffle`

All shufflers operate on train splits only and carry validation/test rows
through unchanged. `TopologyAwareShuffle` rejects candidates whose topology loss
exceeds the configured threshold. `IMFShuffle` is an identity fallback when IMF
decomposition dependencies are unavailable, and decomposition reports
reconstruction error when components exist.

TDA support starts with `LightweightTDAValidator`, a dependency-free path
variation proxy. Future TDA libraries should be optional and feature-flagged.

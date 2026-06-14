# MarketLab Leakage Rules

MarketLab windows are built for local research only. The core invariants are:

- Feature rows must come before validation and test label timestamps.
- Purged walk-forward validation leaves an embargo gap between train and
  validation.
- Horizon-aware labels record both feature index and label index.
- Synthetic rows, including TimeGAN-style generated rows, are train-only and
  never eligible for validation or test.
- Graph snapshots use observations at or before their `as_of` date.

These rules are implemented in services, not new Django models, so future
MarketLab work can reuse shared quant artifacts.

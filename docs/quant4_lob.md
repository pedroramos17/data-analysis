# Quant4 LOB Lab

Quant4 LOB Lab is a local-first limit-order-book and microstructure research
layer under the shared `quant4` app. It normalizes provided equities, futures,
crypto, and venue-dependent FX book data into common snapshots, then builds
past-only feature rows and horizon-aware labels.

## Features And Labels

The feature set includes best bid, best ask, mid price, spread, microprice,
weighted mid, order imbalance, depth imbalance, queue imbalance, slope of book,
bid/ask pressure, realized spread, effective spread, price impact, and book
resilience. Feature rows record their source timestamps so tests can verify they
do not include future book states.

Labels are generated separately and may look forward by the requested horizon.
They include next mid-price movement, h-step return and direction, spread
widening, liquidity vacuum, short-horizon drawdown, and an execution cost
estimate. These are research labels, not trading instructions.

## Models And Commands

The default models are dependency-light baselines: naive order imbalance and a
small logistic-style imbalance baseline. DeepLOB and TCN-LOB are optional stubs
behind PyTorch feature flags and fail clearly when dependencies are missing.

```bash
python manage.py quant4_ingest_lob --input-path data/books.jsonl --venue-type crypto
python manage.py quant4_train_lob_model --input-path data/books.jsonl --data-start 2024-01-01 --data-end 2024-01-01 --split-start 2024-01-01 --split-end 2024-01-01
```

`quant4_train_lob_model` stores metrics and artifact paths in a shared `LOBRun`.
No broker, live-trading, or paid API integration is included.

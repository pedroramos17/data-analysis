# Quant4 Multifractal Models

The model layer in `quant4/services/multifractal/models/` is research-only.
It supports local simulations and calibration diagnostics for MSM, MMAR, and
MRW-style workflows. It does not connect to brokers, place orders, or claim
predictive performance.

Current scope:

- `msm.py`: seeded Markov-switching multifractal volatility simulation,
  parameter validation, and volatility forecast summaries.
- `mmar.py`: seeded MMAR path simulation plus an explicit calibration
  placeholder when a full calibration routine is not available.
- `mrw.py`: seeded multifractal random-walk-style simulation and an
  intermittency proxy derived from empirical scaling behavior.

Randomized paths use named defaults from
`quant4.services.multifractal.defaults` where shared configuration is needed.
Callers can still pass explicit seeds for reproducible experiments.

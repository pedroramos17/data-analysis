# Quant4 Multifractal Quality Gates

The Phase 15 helpers define the local validation matrix for the multifractal
module:

```powershell
.\.venv-win\Scripts\python.exe manage.py check
.\.venv-win\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv-win\Scripts\python.exe manage.py test quant4
.\.venv-win\Scripts\python.exe manage.py test
.\.venv-win\Scripts\ruff.exe check quant4
```

Synthetic generators are deterministic with explicit seeds and cover Gaussian
random walks, autocorrelated fractional-like noise placeholders, multiplicative
cascades, regime-switching volatility, heavy-tailed returns, price-volume
pairs, and synthetic LOB event streams.

The gates are research validation only and include no live-trading or broker
commands.

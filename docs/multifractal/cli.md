# Quant4 Multifractal CLI

All commands run locally through Django management commands. They do not fetch
market data or call paid APIs.

```powershell
python manage.py quant4_import_bars --csv .\bars.csv --symbol SPY --output-root data\mf_bars
python manage.py quant4_compute_returns --bars-root data\mf_bars --output-root data\mf_returns
python manage.py quant4_mfdfa --series "0.01,-0.02,0.015,-0.005"
python manage.py quant4_mf_diagnostics --series "0.01,-0.02,0.015,-0.005"
python manage.py quant4_mf_features --symbol SPY --window-id w0 --series "0.01,-0.02,0.015,-0.005"
python manage.py quant4_mf_risk --series "0.01,-0.02,0.015,-0.005"
python manage.py quant4_mf_regime --series "0.01,-0.02,0.015,-0.005"
python manage.py quant4_mf_portfolio --symbols SPY,QQQ --variances "0.02,0.04"
python manage.py quant4_mf_report --symbol SPY
```

The outputs are research diagnostics. They are not predictions, investment
advice, factor-validity claims, or trading signals.

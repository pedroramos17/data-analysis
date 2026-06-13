# API Facade

The Phase 11 API facade exposes local and cheap-cloud quant workflows through a
provider-backed FastAPI app. Routes call `src.providers.build_provider_registry()`
and do not branch on local versus cloud storage or SQLite versus Postgres.

## Run

```powershell
uvicorn src.api.main:app --host 0.0.0.0 --port 8001
```

OpenAPI docs are available at:

```text
http://127.0.0.1:8001/docs
```

## Endpoints

- `GET /health`
- `GET /config/runtime`
- `POST /ingest/run`
- `POST /features/build`
- `POST /models/train`
- `POST /models/predict`
- `POST /backtest/run`
- `POST /risk/run`
- `GET /assets`
- `GET /signals`
- `GET /backtests/{id}`
- `GET /risk/{id}`
- `GET /models`
- `GET /storage/presign`

Heavy operations are queued/planned by default. Small MVP runs can execute
synchronously by passing `"sync": true` when a real local handler exists, such as
feature builds or baseline model train/predict.

Example async feature build manifest:

```json
{
  "version": "phase10_v1",
  "groups": ["price_volume", "risk"],
  "universe": ["SPY"],
  "sync": false
}
```

Example synchronous baseline prediction:

```json
{
  "sync": true,
  "model_name": "naive_return",
  "feature_set_version": "phase14_v1",
  "train_dataset": [
    {"symbol": "SPY", "ts": "2024-01-01", "log_return": 0.01}
  ],
  "dataset": [
    {"symbol": "SPY", "ts": "2024-01-02"}
  ],
  "horizon": "1d"
}
```

Prediction responses and `GET /signals` rows include `explanation_json` so
signals are not black-box-only. The explanation payload includes model/version,
feature-store version, top feature proxies, horizon, confidence, uncertainty,
regime/risk context, and data-quality flags.

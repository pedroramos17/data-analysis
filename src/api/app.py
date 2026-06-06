"""FastAPI app factory for the provider-backed API facade."""

from __future__ import annotations

from collections.abc import Mapping

import src.api.handlers as handlers
from src.providers.registry import ProviderRegistry


def create_app(registry: ProviderRegistry | None = None) -> object:
    """Create the FastAPI application.

    FastAPI is imported lazily so non-API local workflows do not need it unless
    they start the API facade or run OpenAPI smoke tests.
    """
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError(
            "fastapi is required for the API facade; expected installed module"
        ) from exc

    from src.security.auth import authenticate_request
    from src.security.api_keys import extract_api_key
    from src.security.rate_limit import RateLimitIdentity, RateLimitPolicy, RateLimitRequest

    active_registry = registry or handlers.default_registry()
    rate_limit_policy = RateLimitPolicy(active_registry.settings.rate_limit)
    app = FastAPI(
        title="Quant MVP API Facade",
        version="0.11.0",
        description="Provider-neutral API for local and cheap-cloud quant workflows.",
    )
    if active_registry.settings.security.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(active_registry.settings.security.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        )

    def security_principal(
        request: Request,
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        authorization: str | None = Header(None),
    ) -> str:
        result = authenticate_request(
            request.url.path,
            request.method,
            active_registry.settings,
            api_key_header=x_api_key,
            authorization_header=authorization,
        )
        if not result.allowed:
            raise HTTPException(status_code=result.status_code, detail=result.reason)
        api_key = extract_api_key(x_api_key) or extract_api_key(authorization)
        rate_limit = rate_limit_policy.check(
            RateLimitRequest(
                request.url.path,
                method=request.method,
                identity=RateLimitIdentity(
                    ip_address=request.client.host if request.client else "unknown",
                    api_key=api_key,
                    authenticated=result.principal != "anonymous",
                ),
                cost=2 if request.url.path.rstrip("/") in {"/compute/runpod/submit", "/compute/runpod/cancel"} else 1,
            )
        )
        if not rate_limit.allowed:
            raise HTTPException(status_code=429, detail=rate_limit.message, headers=rate_limit.headers())
        return result.principal

    @app.get("/health")
    def health(principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.health(active_registry)

    @app.get("/config/runtime")
    def config_runtime(principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.runtime_config(active_registry)

    @app.get("/runtime")
    def runtime(principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.runtime_config(active_registry)

    @app.get("/pipeline/runs")
    def pipeline_runs(
        limit: int = Query(50, ge=0, le=500),
        status: str = "",
        principal: str = Depends(security_principal),
    ) -> dict[str, object]:
        return handlers.pipeline_runs(active_registry, limit=limit, status=status)

    @app.post("/pipeline/run")
    def pipeline_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.pipeline_run(active_registry, _payload(payload))

    @app.post("/pipeline/dry-run")
    def pipeline_dry_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.pipeline_dry_run(active_registry, _payload(payload))

    @app.post("/ingest/run")
    def ingest_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.ingest_run(active_registry, _payload(payload))

    @app.post("/preprocess/run")
    def preprocess_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.preprocess_run(active_registry, _payload(payload))

    @app.post("/features/build")
    def features_build(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.features_build(active_registry, _payload(payload))

    @app.post("/windows/build")
    def windows_build(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.windows_build(active_registry, _payload(payload))

    @app.post("/train/run")
    def train_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.train_run(active_registry, _payload(payload))

    @app.post("/evaluate/run")
    def evaluate_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.evaluate_run(active_registry, _payload(payload))

    @app.post("/models/train")
    def models_train(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.models_train(active_registry, _payload(payload))

    @app.post("/models/predict")
    def models_predict(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.models_predict(active_registry, _payload(payload))

    @app.post("/backtest/run")
    def backtest_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.backtest_run(active_registry, _payload(payload))

    @app.post("/risk/run")
    def risk_run(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.risk_run(active_registry, _payload(payload))

    @app.post("/cost/estimate")
    def cost_estimate(payload: dict[str, object] | None = None, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.cost_estimate(active_registry, _payload(payload))

    @app.post("/compute/runpod/dry-run")
    def compute_runpod_dry_run(
        payload: dict[str, object] | None = None,
        principal: str = Depends(security_principal),
    ) -> dict[str, object]:
        return handlers.compute_runpod_dry_run(active_registry, _payload(payload), principal=principal)

    @app.post("/compute/runpod/submit")
    def compute_runpod_submit(
        payload: dict[str, object] | None = None,
        principal: str = Depends(security_principal),
    ) -> dict[str, object]:
        return handlers.compute_runpod_submit(active_registry, _payload(payload), principal=principal)

    @app.post("/compute/runpod/cancel")
    def compute_runpod_cancel(
        payload: dict[str, object] | None = None,
        principal: str = Depends(security_principal),
    ) -> dict[str, object]:
        return handlers.compute_runpod_cancel(active_registry, _payload(payload), principal=principal)

    @app.get("/assets")
    def assets(limit: int = Query(100, ge=0, le=500), principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.assets(active_registry, limit)

    @app.get("/signals")
    def signals(limit: int = Query(100, ge=0, le=500), principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.signals(active_registry, limit)

    @app.get("/backtests/{id}")
    def backtest(id: int, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.backtest(active_registry, id)

    @app.get("/risk/{id}")
    def risk(id: int, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.risk(active_registry, id)

    @app.get("/models")
    def models(principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.models(active_registry)

    @app.get("/storage/presign")
    def storage_presign(
        path: str,
        expires_seconds: int = Query(300, ge=1, le=3600),
        principal: str = Depends(security_principal),
    ) -> dict[str, object]:
        return handlers.storage_presign(active_registry, path, expires_seconds)

    @app.get("/efficiency/{run_id}")
    def efficiency(run_id: int, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.efficiency(active_registry, run_id)

    @app.get("/reports/{run_id}")
    def reports(run_id: int, principal: str = Depends(security_principal)) -> dict[str, object]:
        return handlers.reports(active_registry, run_id)

    return app


def _payload(payload: Mapping[str, object] | None) -> dict[str, object]:
    return dict(payload or {})

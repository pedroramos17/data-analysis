"""Admin registrations for Quant4 metadata models."""

from __future__ import annotations

from django.contrib import admin

from quant4.models import (
    Asset,
    BacktestRun,
    Experiment,
    ExplainabilityReport,
    FeatureArtifact,
    GraphSnapshot,
    LOBRun,
    MarketDataset,
    ModelRun,
    PortfolioRun,
    RegimeRun,
    RiskRun,
    WindowArtifact,
)

admin.site.register(Asset)
admin.site.register(MarketDataset)
admin.site.register(Experiment)
admin.site.register(WindowArtifact)
admin.site.register(FeatureArtifact)
admin.site.register(RegimeRun)
admin.site.register(RiskRun)
admin.site.register(LOBRun)
admin.site.register(GraphSnapshot)
admin.site.register(PortfolioRun)
admin.site.register(ModelRun)
admin.site.register(BacktestRun)
admin.site.register(ExplainabilityReport)

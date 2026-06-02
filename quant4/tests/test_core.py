"""Quant4 registry-first core tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from django.test import TestCase, override_settings


class Quant4AssetRegistryTests(TestCase):
    """Asset and dataset metadata should be registry-first and idempotent."""

    def test_asset_registry_creates_assets(self) -> None:
        """Registering asset payloads creates local Asset rows."""
        from quant4.models import Asset
        from quant4.services.assets import register_assets

        register_assets(
            [
                {
                    "symbol": "AAPL",
                    "asset_type": "equity",
                    "name": "Apple Inc.",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                }
            ],
            provenance={"source": "unit-test"},
        )

        asset = Asset.objects.get(symbol="AAPL")
        self.assertEqual(asset.exchange, "NASDAQ")
        self.assertEqual(asset.provenance_json["source"], "unit-test")

    def test_duplicate_assets_are_handled_idempotently(self) -> None:
        """Registering the same asset twice updates instead of duplicating."""
        from quant4.models import Asset
        from quant4.services.assets import register_assets

        payload = {
            "symbol": "MSFT",
            "asset_type": "equity",
            "name": "Microsoft",
            "exchange": "NASDAQ",
            "currency": "USD",
        }

        register_assets([payload], provenance={"source": "first"})
        register_assets([payload | {"name": "Microsoft Corp."}])

        self.assertEqual(Asset.objects.filter(symbol="MSFT").count(), 1)
        self.assertEqual(Asset.objects.get(symbol="MSFT").name, "Microsoft Corp.")

    def test_market_dataset_metadata_is_saved(self) -> None:
        """Dataset ingestion records metadata without storing heavy rows."""
        from quant4.services.assets import register_assets
        from quant4.services.data_ingestion import save_market_dataset_metadata

        asset = register_assets([{"symbol": "SPY", "asset_type": "etf"}]).assets[0]
        dataset = save_market_dataset_metadata(
            name="spy-daily",
            source="local-csv",
            frequency="1d",
            asset=asset,
            metadata={"rows": 252},
            provenance={"path": "sample_data/spy.csv"},
        )

        self.assertEqual(dataset.metadata_json["rows"], 252)
        self.assertEqual(dataset.provenance_json["path"], "sample_data/spy.csv")


class Quant4ArtifactTests(TestCase):
    """Artifacts and runs must store reproducibility metadata."""

    def test_window_artifacts_store_split_metadata(self) -> None:
        """Window preparation stores split and provenance metadata."""
        from quant4.services.data_ingestion import save_market_dataset_metadata
        from quant4.services.windows import create_window_artifact

        dataset = save_market_dataset_metadata(
            name="prices",
            source="fixture",
            frequency="1d",
        )

        artifact = create_window_artifact(
            dataset=dataset,
            name="walk-forward-1",
            split_metadata={"train": ["2024-01-01", "2024-06-30"]},
            config={"window": "walk-forward"},
            random_seed=7,
            data_range=(date(2024, 1, 1), date(2024, 12, 31)),
            split_range=(date(2024, 7, 1), date(2024, 9, 30)),
            provenance={"builder": "unit-test"},
        )

        self.assertEqual(artifact.random_seed, 7)
        self.assertEqual(artifact.split_metadata_json["train"][0], "2024-01-01")
        self.assertEqual(artifact.provenance_json["builder"], "unit-test")

    def test_run_models_expose_reproducibility_fields(self) -> None:
        """All Quant4 run records keep hash, seed, ranges, and provenance."""
        from quant4.models import (
            BacktestRun,
            ExplainabilityReport,
            FeatureArtifact,
            GraphSnapshot,
            LOBRun,
            ModelRun,
            PortfolioRun,
            RegimeRun,
            RiskRun,
            WindowArtifact,
        )

        required = {
            "config_hash",
            "random_seed",
            "data_start",
            "data_end",
            "split_start",
            "split_end",
            "feature_schema_json",
            "provenance_json",
        }

        for model in (
            WindowArtifact,
            FeatureArtifact,
            RegimeRun,
            RiskRun,
            LOBRun,
            GraphSnapshot,
            PortfolioRun,
            ModelRun,
            BacktestRun,
            ExplainabilityReport,
        ):
            with self.subTest(model=model.__name__):
                field_names = {field.name for field in model._meta.fields}
                self.assertTrue(required.issubset(field_names))

    def test_run_metadata_rejects_split_outside_data_range(self) -> None:
        """Run metadata ranges fail closed when split dates exceed data dates."""
        from quant4.services.run_metadata import build_run_metadata_fields

        with self.assertRaisesRegex(ValueError, "split_range"):
            build_run_metadata_fields(
                data_range=(date(2024, 1, 1), date(2024, 1, 31)),
                split_range=(date(2024, 2, 1), date(2024, 2, 5)),
                random_seed=3,
                provenance={"test": "unit"},
            )


class Quant4SafetyTests(TestCase):
    """Leakage and registry failures should fail closed with clear messages."""

    def test_leakage_checker_rejects_future_feature_timestamps(self) -> None:
        """Feature timestamps after labels are rejected."""
        from quant4.services.leakage import assert_no_future_feature_timestamps

        with self.assertRaisesRegex(ValueError, "2024-01-03"):
            assert_no_future_feature_timestamps(
                [
                    {
                        "feature_timestamp": datetime(2024, 1, 3, tzinfo=UTC),
                        "label_timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    }
                ]
            )

    @override_settings(SOURCEFLOW_FEATURE_FLAGS={"QUANT4_MODEL_BASELINE": False})
    def test_registry_can_enable_disable_components(self) -> None:
        """Feature flags disable registered components by name."""
        from quant4.services.registry import (
            ComponentRegistry,
            ComponentSpec,
            DisabledComponentError,
        )

        registry = ComponentRegistry()
        registry.register(
            ComponentSpec(
                name="baseline",
                category="models",
                factory=dict,
                feature_flag="QUANT4_MODEL_BASELINE",
            )
        )

        self.assertFalse(registry.is_enabled("models", "baseline"))
        with self.assertRaisesRegex(DisabledComponentError, "baseline"):
            registry.resolve("models", "baseline")

    def test_default_registry_names_every_component_category(self) -> None:
        """Default registry entries cover every required category by name."""
        from quant4.services.registry import (
            COMPONENT_CATEGORIES,
            build_default_registry,
        )

        registry = build_default_registry()

        for category in COMPONENT_CATEGORIES:
            with self.subTest(category=category):
                self.assertGreater(len(registry.registered_names(category)), 0)

    def test_missing_optional_component_returns_clear_error(self) -> None:
        """Missing optional imports identify the component and dependency."""
        from quant4.services.registry import (
            ComponentRegistry,
            ComponentSpec,
            OptionalDependencyMissingError,
        )

        registry = ComponentRegistry()
        registry.register(
            ComponentSpec(
                name="tda-denoiser",
                category="denoisers",
                factory=dict,
                required_import="missing_quant4_optional_dependency",
            )
        )

        with self.assertRaisesRegex(
            OptionalDependencyMissingError,
            "missing_quant4_optional_dependency",
        ):
            registry.resolve("denoisers", "tda-denoiser")

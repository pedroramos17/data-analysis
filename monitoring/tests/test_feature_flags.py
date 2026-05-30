"""Tests for Sourceflow finance feature flags."""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase, override_settings


class FeatureFlagTests(TestCase):
    """Feature flag registry must gate experimental finance code."""

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"FIN_MODEL_MCI_GRU": False},
    )
    def test_disabled_experimental_feature_raises(self) -> None:
        """Disabled model flags fail before prototype code can run."""
        from sourceflow.config.feature_flags import (
            FeatureDisabledError,
            require_feature,
        )

        with self.assertRaisesRegex(FeatureDisabledError, "FIN_MODEL_MCI_GRU"):
            require_feature("FIN_MODEL_MCI_GRU")

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"FIN_DATA_CORE": False},
    )
    def test_settings_override_default_flag(self) -> None:
        """Django settings override code defaults for test isolation."""
        from sourceflow.config.feature_flags import feature_flag_enabled

        self.assertFalse(feature_flag_enabled("FIN_DATA_CORE"))

    def test_sqlite_flag_override_is_visible_to_commands(self) -> None:
        """The set/list commands round-trip flag state through SQLite."""
        from io import StringIO

        set_output = StringIO()
        list_output = StringIO()

        call_command(
            "set_feature_flag",
            "FIN_MODEL_GNN",
            "true",
            stdout=set_output,
        )
        call_command("list_feature_flags", stdout=list_output)

        self.assertIn("FIN_MODEL_GNN=true", set_output.getvalue())
        self.assertIn("FIN_MODEL_GNN", list_output.getvalue())
        self.assertIn("sqlite", list_output.getvalue())


class ModelFeatureGateTests(TestCase):
    """Heavy model specs must respect feature flags."""

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"FIN_MODEL_EXPERIMENTAL_TORCH": False},
    )
    def test_torch_prototype_is_not_constructed_when_disabled(self) -> None:
        """The torch prototype entrypoint is guarded before importing torch."""
        from sourceflow.config.feature_flags import FeatureDisabledError
        from sourceflow.finance_models.mci_gru_gnn_spec import build_torch_prototype

        with self.assertRaisesRegex(
            FeatureDisabledError, "FIN_MODEL_EXPERIMENTAL_TORCH"
        ):
            build_torch_prototype()

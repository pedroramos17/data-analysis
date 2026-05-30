"""Name-based component registry for Quant4 research services."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sourceflow.config.feature_flags import feature_flag_enabled

COMPONENT_CATEGORIES = frozenset(
    {
        "models",
        "risk_models",
        "graph_builders",
        "optimizers",
        "shufflers",
        "denoisers",
        "regime_detectors",
    }
)


class RegistryError(RuntimeError):
    """Base registry failure for clear local error reporting.

    Example:
        `raise RegistryError("Invalid component")`
    """


class DisabledComponentError(RegistryError):
    """Raised when a feature flag disables a registered component.

    Example:
        `registry.resolve("models", "baseline")`
    """


class OptionalDependencyMissingError(RegistryError):
    """Raised when an optional dependency is needed but unavailable.

    Example:
        `registry.resolve("denoisers", "tda")`
    """


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """Declarative registry entry for a Quant4 component.

    Example:
        `ComponentSpec(name="baseline", category="models", factory=dict)`
    """

    name: str
    category: str
    factory: Callable[[], object]
    feature_flag: str = "QUANT4_CORE"
    required_import: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


class ComponentRegistry:
    """In-memory registry keyed by category and component name.

    Example:
        `registry.register(ComponentSpec("baseline", "models", dict))`
    """

    def __init__(
        self,
        feature_checker: Callable[[str], bool] = feature_flag_enabled,
    ) -> None:
        self._feature_checker = feature_checker
        self._specs: dict[str, dict[str, ComponentSpec]] = {}

    def register(self, spec: ComponentSpec) -> None:
        """Register one named component spec.

        Example:
            `registry.register(ComponentSpec("baseline", "models", dict))`
        """
        _validate_category(spec.category)
        _validate_name(spec.name, "component name")
        self._specs.setdefault(spec.category, {})[spec.name] = spec

    def registered_names(self, category: str) -> list[str]:
        """Return registered component names for a category.

        Example:
            `registry.registered_names("models")`
        """
        _validate_category(category)
        return sorted(self._specs.get(category, {}))

    def is_enabled(self, category: str, name: str) -> bool:
        """Return whether a registered component is flag-enabled.

        Example:
            `registry.is_enabled("models", "baseline")`
        """
        spec = self._get_spec(category, name)
        return self._feature_checker(spec.feature_flag)

    def resolve(self, category: str, name: str) -> object:
        """Instantiate an enabled component or raise a clear error.

        Example:
            `model = registry.resolve("models", "baseline")`
        """
        spec = self._get_spec(category, name)
        _require_enabled(spec, self._feature_checker)
        _require_optional_dependency(spec)
        return spec.factory()

    def _get_spec(self, category: str, name: str) -> ComponentSpec:
        _validate_category(category)
        category_specs = self._specs.get(category, {})
        if name in category_specs:
            return category_specs[name]
        raise RegistryError(
            f"Unknown component {name!r} in {category!r}; "
            f"expected one of {sorted(category_specs)}"
        )


def stable_config_hash(config: Mapping[str, object]) -> str:
    """Return a stable sha256 hash for a run config.

    Example:
        `stable_config_hash({"window": "walk-forward"})`
    """
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_default_registry() -> ComponentRegistry:
    """Return the default local registry with safe baseline components.

    Example:
        `registry = build_default_registry()`
    """
    registry = ComponentRegistry()
    for spec in _default_specs():
        registry.register(spec)
    return registry


def _default_specs() -> list[ComponentSpec]:
    return [
        ComponentSpec("baseline", "models", dict, "QUANT4_MODEL_BASELINE"),
        ComponentSpec("variance", "risk_models", dict, "QUANT4_RISK_MODELS"),
        ComponentSpec("correlation", "graph_builders", dict, "QUANT4_GRAPH_BUILDERS"),
        ComponentSpec("mean_variance", "optimizers", dict, "QUANT4_OPTIMIZERS"),
        ComponentSpec("walk_forward", "shufflers", dict, "QUANT4_SHUFFLERS"),
        ComponentSpec("identity", "denoisers", dict, "QUANT4_DENOISERS"),
        ComponentSpec(
            "threshold",
            "regime_detectors",
            dict,
            "QUANT4_REGIME_DETECTORS",
        ),
    ]


def _require_enabled(
    spec: ComponentSpec,
    feature_checker: Callable[[str], bool],
) -> None:
    if feature_checker(spec.feature_flag):
        return
    raise DisabledComponentError(
        f"Component {spec.name!r} is disabled by {spec.feature_flag}; expected enabled"
    )


def _require_optional_dependency(spec: ComponentSpec) -> None:
    if not spec.required_import:
        return
    try:
        importlib.import_module(spec.required_import)
    except ImportError as exc:
        raise OptionalDependencyMissingError(
            f"Component {spec.name!r} requires optional dependency "
            f"{spec.required_import!r}; expected installed module"
        ) from exc


def _validate_category(category: str) -> None:
    if category in COMPONENT_CATEGORIES:
        return
    raise RegistryError(
        f"Invalid registry category {category!r}; expected one of "
        f"{sorted(COMPONENT_CATEGORIES)}"
    )


def _validate_name(value: str, label: str) -> None:
    if value.strip():
        return
    raise RegistryError(f"Invalid {label} {value!r}; expected non-empty string")

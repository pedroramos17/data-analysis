# Quant4 Registry

Quant4 uses a registry-first architecture for components that can vary by
experiment. Components are registered by category and name before they are used.

Initial registry categories:

- `models`
- `risk_models`
- `graph_builders`
- `optimizers`
- `shufflers`
- `denoisers`
- `regime_detectors`

`quant4.services.registry.ComponentRegistry` stores `ComponentSpec` entries with
these fields:

- `name`
- `category`
- `factory`
- `feature_flag`
- `required_import`
- `metadata`

Feature flags are resolved through the shared Sourceflow flag path: Django
settings, environment, SQLite override, then code default. Disabled components
raise `DisabledComponentError`. Missing optional imports raise
`OptionalDependencyMissingError` and include the component and missing module in
the message.

Default Quant4 flags live in `sourceflow/config/default_flags.py`:

- `QUANT4_CORE`
- `QUANT4_DATA_FOUNDATION`
- `QUANT4_REGISTRY`
- `QUANT4_MODEL_BASELINE`
- `QUANT4_RISK_MODELS`
- `QUANT4_GRAPH_BUILDERS`
- `QUANT4_OPTIMIZERS`
- `QUANT4_SHUFFLERS`
- `QUANT4_DENOISERS`
- `QUANT4_REGIME_DETECTORS`

Registry resolution never validates research quality or factor validity. It only
selects an enabled local component.

# Handoff: Phase 0-2 Finance/Quant Boundary Refactor

## Current State

### Completed Work

1. Phase 1 - Rename Legacy Quant App to Quant
   - `quant4/` renamed to `quant/`
   - Management commands renamed from `quant4_*` to `quant_*`
   - Feature flags renamed from `QUANT4_*` to `QUANT_*`
   - Stale documentation removed
   - Clean grep for stale names

2. Phase 0 - Inventory and Freeze Points
   - Created `docs/finance_quant_inventory.md` with full file classification
   - Documented action taxonomy: KEEP_AS_IS, MERGE_INTO_WAREHOUSE, MERGE_INTO_FINANCE_CORE, MOVE_TO_QUANT, etc.
   - Listed command coverage, test boundaries, and stale doc decisions

3. Phase 2 - Finance Core Contracts
   - Created `sourceflow/finance_core/` with:
     - `contracts.py` (BarRecord, InstrumentRef, MarketBarPoint, etc.)
     - `time.py` (require_datetime, UTC normalization)
     - `ids.py` (stable_id)
     - `enums.py` (DataLayer, AssetClass)
     - `schemas.py` (BAR_SCHEMA_VERSION)
   - Created `sourceflow/warehouse/` with:
     - `parquet_io.py`, `manifests.py`, `paths.py`, `atomic_write.py`
   - Moved shared market contracts from `sourceflow/intelligence/market/contracts.py` → `sourceflow/finance_core/contracts.py`
   - Bridged quant multifractal OHLCV bars: `OHLCVBar = BarRecord`
   - Updated all imports
   - Added `sourceflow/finance_core/tests/test_contracts.py` (4 passing tests)

### Remaining TODO

- **Phase 3**: Finish warehouse consolidation (move parquet_store, sqlite_registry)
- **Phase 4**: Build provider-neutral ingestion with `finance_ingestion.providers/`
- **Phase 5**: Clean dataset boundary (keep leakage/splits/targets, remove providers)
- **Phase 6**: Add deterministic feature registry and TIN equality tests
- **Phase 7**: Refactor quant research boundary (engines, backtesting, RL)
- **Phase 8**: Implement stable command chain (build_market_layer, build_finance_features, etc.)
- **Phase 9**: Final docs/dead code cleanup

### Django Dependency Issue

Django checks/tests are blocked in this environment (`ModuleNotFoundError: No module named 'django'`).
When environment has Django installed, run:
```bash
python3 manage.py check
python3 manage.py test quant researchspace monitoring.tests.test_research_cookbook
```

### Files in This PR

- Modified: configs, settings, imports, docs
- Deleted: `quant4/` (entire old package), `quantspace/` (entire old package), stale docs
- Added: `quant/`, `researchspace/`, `sourceflow/finance_core/`, `sourceflow/warehouse/`, new docs

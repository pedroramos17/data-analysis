# Multifractal Phases 6-15 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Quant4 multifractal phases 6 through 15 as local-first, CPU-friendly modules.

**Architecture:** Continue under `quant4/services/multifractal/`, using SQLite metadata models already in `quant4.models` and Parquet for feature/report artifacts. Each phase lands as a separate tested commit.

**Tech Stack:** Python standard library, Django tests, existing PyArrow boundary, optional dependency adapters only where already requested.

---

### Task 6: Multifractal Research Models

**Files:** `quant4/services/multifractal/models/{mmar,msm,mrw}.py`, `quant4/tests/test_multifractal_models.py`

- [ ] Write tests for seeded simulations, parameter validation, MSM volatility forecast, MMAR calibration placeholder, and MRW intermittency estimate.
- [ ] Run `python manage.py test quant4.tests.test_multifractal_models` and confirm missing modules fail.
- [ ] Implement pure-Python simulation/calibration interfaces.
- [ ] Run targeted tests, Ruff, `manage.py check`, `manage.py test quant4`, and commit.

### Task 7: Feature Engineering And Store

**Files:** `quant4/services/multifractal/features/{multifractal_features,feature_store}.py`, `quant4/tests/test_multifractal_features_store.py`

- [ ] Test rolling/core/cross features, config hash persistence, Parquet feature matrix, and SQLite `FeatureArtifact`.
- [ ] Implement no-lookahead feature builders and Parquet feature store.
- [ ] Validate and commit.

### Task 8: Risk Assessment

**Files:** `quant4/services/multifractal/risk/{multifractal_risk,var,stress,reports}.py`, `quant4/tests/test_multifractal_risk.py`

- [ ] Test VaR confidence monotonicity, risk score response to volatility/intermittency, no-lookahead rolling risk, and JSON/Markdown reports.
- [ ] Implement traditional and multifractal risk components with clear no-prediction framing.
- [ ] Validate and commit.

### Task 9: Regime Detection

**Files:** `quant4/services/multifractal/regime/{multifractal_regime,change_points}.py`, `quant4/tests/test_multifractal_regime.py`

- [ ] Test synthetic regime shift detection, label stability under small noise, and no future leakage.
- [ ] Implement rule-based labels and CUSUM/rolling z-score change points with optional sklearn-free fallback.
- [ ] Validate and commit.

### Task 10: Portfolio Integration

**Files:** `quant4/services/multifractal/portfolio/{multifractal_optimizer,objectives,constraints}.py`, `quant4/tests/test_multifractal_portfolio.py`

- [ ] Test weights sum, constraints, turbulent risk penalty, and risk contribution outputs.
- [ ] Implement minimum variance, risk parity, multifractal penalty, regime-aware caps, and network-cluster penalty.
- [ ] Validate and commit.

### Task 11: LOB Readiness

**Files:** `quant4/services/multifractal/lob/{contracts,features,multifractal_lob}.py`, `quant4/tests/test_multifractal_lob.py`

- [ ] Test synthetic LOB schema, spread/imbalance/event-duration features, and MF-DFA/MF-DCCA transforms.
- [ ] Implement interfaces without requiring venue depth data.
- [ ] Validate and commit.

### Task 12: ML Integration

**Files:** `quant4/services/multifractal/ml/{datasets,baselines,evaluation}.py`, `quant4/tests/test_multifractal_ml.py`

- [ ] Test walk-forward datasets, no random time split, optional sklearn baselines, and metrics without performance claims.
- [ ] Implement CPU-friendly dataset builder and deterministic baseline fallbacks.
- [ ] Validate and commit.

### Task 13: CLI Commands

**Files:** `quant4/management/commands/quant4_mf_*.py`, `quant4/tests/test_multifractal_cli.py`

- [ ] Test command smoke paths for import, returns, MF-DFA, diagnostics, features, risk, regime, portfolio, and report.
- [ ] Implement Django commands using existing service boundaries.
- [ ] Validate and commit.

### Task 14: Reporting And Visualization

**Files:** `quant4/services/multifractal/reports/multifractal_report.py`, `quant4/services/multifractal/plots/multifractal_plots.py`, `quant4/tests/test_multifractal_reporting.py`

- [ ] Test markdown report sections and matplotlib/fallback plot artifact creation.
- [ ] Implement Markdown-first reporting and optional matplotlib plots with clear cautions.
- [ ] Validate and commit.

### Task 15: Quality Gates And Synthetic Generators

**Files:** `quant4/services/multifractal/synthetic.py`, `quant4/services/multifractal/quality_gates.py`, `quant4/tests/test_multifractal_quality_gates.py`

- [ ] Test synthetic generators, quality gate command matrix, and integration smoke over all modules.
- [ ] Implement reusable synthetic data generators and local quality gate helpers.
- [ ] Run final full validation and commit.

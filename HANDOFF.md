# Project Handoff

Date: 2026-06-11

Project: `github.com/pedroramos17/data-analysis`

Working directory: `/home/pedro/dev/data-analysis`

Branch: `codex/quant-ml-mvp-publish-readiness`

Latest commits:

- `495fed4 docs: add deployment and acceptance readiness`
- `a342cca feat: add quant ml pipeline orchestration`
- `e8d6029 feat: add provider-backed runtime foundation`
- `2e599d8 Merge pull request #8 from pedroramos17/codex/quant4-multifractal-refactor`
- `0c9dd30 Merge branch 'main' into codex/quant4-multifractal-refactor`

## Current Goal

Incrementally upgrade the repo into an Agentic Knowledge Reasoning, GraphRAG,
and Quant 4.0 system without rewriting existing working code.

The current implementation track is the additive `sourceflow` canonical
knowledge layer. Phases 0 through 10 are implemented and targeted tests pass.

## Constraints To Preserve

- Keep existing `monitoring`, `quant4`, `quantspace`, CLI, API, and data paths working.
- Add adapters and interfaces before replacing behavior.
- Every extracted object must carry provenance.
- Every inferred belief must carry justification.
- Do not use global closed-world assumption for news.
- Do not collapse contradictory claims into one truth value.
- Prefer local-first, SQL-backed implementations before adding advanced backends.
- Use `.venv` from Linux. `.venv-win/Scripts/python.exe` exists but failed with `Permission denied`.

## Implemented Work

### Phase 0 - Architecture Contract

- Added architecture docs under `docs/architecture/`:
  - `current_state.md`
  - `target_state.md`
  - `migration_plan.md`
  - `module_contracts.md`
- Added additive `sourceflow/` module boundaries.
- Added import contract test in `tests/test_phase0_architecture_contract.py`.

### Phase 1 - Canonical Schema

- Registered additive Django app `sourceflow.apps.SourceflowConfig` in `public_monitor/settings.py`.
- Added canonical models in `sourceflow/models.py`.
- Added admin registration in `sourceflow/admin.py`.
- Added assumption policy helpers in `sourceflow/reasoning/assumptions.py`.
- Added migrations under `sourceflow/migrations/`.
- Added schema tests in `sourceflow/tests/test_phase1_schema.py`.

### Phase 2 - Ingestion And Evidence

- Added document dedupe helpers in `sourceflow/ingestion/dedup.py`.
- Added offset-preserving chunking in `sourceflow/ingestion/chunker.py`.
- Added canonical document normalization and persistence in `sourceflow/ingestion/normalizer.py`.
- Added evidence span creation and provenance lookup in `sourceflow/ingestion/evidence.py`.
- Added tests in `tests/test_phase2_ingestion_utilities.py` and `sourceflow/tests/test_phase2_ingestion.py`.

### Phase 3 - Entity Layer

- Added entity extractor provider contract and heuristic extractor in `sourceflow/entities/extractor.py`.
- Added alias and external identifier registry helpers in `sourceflow/entities/aliases.py`.
- Added context-aware entity resolution, NIL handling, and merge workflow in `sourceflow/entities/resolution.py`.
- Added mention persistence with evidence spans in `sourceflow/entities/linker.py`.
- Added tests in `tests/test_phase3_entity_utilities.py` and `sourceflow/tests/test_phase3_entities.py`.

### Phase 4 - Claims And Events

- Added claim normalization in `sourceflow/claims/normalizer.py`.
- Added claim validation in `sourceflow/claims/validators.py`.
- Added structured claim extraction and persistence in `sourceflow/claims/extractor.py`.
- Added event classification in `sourceflow/events/classifier.py`.
- Added event impact/risk-channel defaults in `sourceflow/events/impact_schema.py`.
- Added actor-predicate-object event extraction and persistence in `sourceflow/events/extractor.py`.
- Added tests in `tests/test_phase4_claim_event_utilities.py` and `sourceflow/tests/test_phase4_extraction.py`.
- Updated `docs/architecture/migration_plan.md` to mark Phase 4 implemented.

### Phase 5 - Knowledge Graph

- Added dependency-light graph schema in `sourceflow/kg/schema.py`: typed
  `GraphNodeRef`, canonical node types, auditable `ALLOWED_EDGES` registry,
  and `validate_edge` rejecting unknown edge types and endpoint pairs.
- Added `GraphStore` protocol and SQL-backed `SqlGraphStore` in
  `sourceflow/kg/store.py` persisting to the canonical `KnowledgeEdge` table.
- Edge writes are idempotent upserts requiring non-empty provenance, with
  confidence and `observed_at` on every edge.
- `upsert_claim`/`upsert_event` map claims and events to subject/actor,
  object, document, source, and evidence-span edges with record provenance.
- Added tests in `tests/test_phase5_kg_utilities.py` and
  `sourceflow/tests/test_phase5_kg.py`.
- Updated `docs/architecture/migration_plan.md` to mark Phase 5 implemented.

### Phase 6 - Truth Maintenance System

- Added dependency-light truth status resolution in `sourceflow/tms/status.py`:
  active justification weights resolve to `true_supported`,
  `partially_supported`, `false_supported`, or `contradicted`; mixed evidence
  marks a dispute and never collapses; with no active evidence the assumption
  policy decides (OWA keeps unknown, CWA infers supported absence).
- Added belief creation in `sourceflow/tms/beliefs.py`: mandatory non-empty
  provenance, resolved `AssumptionPolicy` row, and at least one
  `Justification` row linking supporting/contradicting claims, events,
  beliefs, or rules; `recompute_belief` re-derives truth status from active
  justifications; `justification_is_active` deactivates justifications whose
  claim/belief is retracted, whose event has a retraction audit row, or whose
  rule is disabled.
- Added retraction propagation in `sourceflow/tms/retraction.py`:
  `retract_claim`/`retract_event`/`retract_belief` write `RetractionLog`
  audit rows, transitively mark dependent beliefs stale with per-belief audit
  rows, and `recompute_stale_beliefs` reactivates stale beliefs with fresh
  truth status. Events have no status column, so the audit row is their
  retraction record.
- Added tests in `tests/test_phase6_tms_utilities.py` and
  `sourceflow/tests/test_phase6_tms.py`.
- Updated `docs/architecture/migration_plan.md` to mark Phase 6 implemented.

### Phase 7.1 - Inference Rule Engine

- Added dependency-light rule parsing and matching in `sourceflow/reasoning/rules.py`.
- Added Django-backed inference engine in `sourceflow/reasoning/engine.py`.
- Supported rule types are deductive, default, abductive, diagnostic,
  risk propagation, source comparison, and retrieval expansion.
- Added default YAML rule in `rules/legal_event_increases_risk.yaml`.
- Rule-derived beliefs are created through the TMS, carry `created_by_rule`, and
  get `derived_by_rule` justifications referencing both the persisted rule and
  source support.
- Default-rule exceptions can block defeasible conclusions before belief creation.
- Added tests in `tests/test_phase7_rule_utilities.py` and
  `sourceflow/tests/test_phase7_inference_engine.py`.

### Phase 7.2 - Contradiction And Paraconsistent Handling

- Added contradiction detection in `sourceflow/reasoning/contradictions.py`.
- Conflicting claims are matched by same subject, predicate, and object with
  opposite polarity.
- Both conflicting claims are preserved and marked `disputed` with
  `metadata_json["dispute_status"] = "source_disputed"`.
- Added `contradicts` claim-to-claim KG edges with source and evidence
  provenance.
- The inference engine skips hard truth derivation from source-disputed claim
  support instead of failing globally.

### Phase 7.3 - Abductive Diagnosis

- Added ranked abductive diagnosis in `sourceflow/reasoning/diagnosis.py`.
- Inputs cover price move, volume spike, volatility shock, LOB anomaly,
  negative news cluster, sector divergence, and macro event evidence.
- Outputs include hypothesis, supporting evidence, missing evidence,
  confidence, graph path, and recommended next retrieval.
- Added tests in `tests/test_phase7_contradiction_diagnosis_utilities.py` and
  `sourceflow/tests/test_phase7_contradictions_diagnosis.py`.

### Phase 8 - Source Comparison Machine

- Reused existing `ProviderOwner` and `Source` reliability metadata fields;
  no migration was needed.
- Added source grouping and reliability metadata helpers in
  `sourceflow/analysis/source_bias.py`.
- Sources can be grouped by owner, provider, region, ideology/business category,
  and content type.
- Added event clustering in `sourceflow/events/clustering.py`.
- Added source-by-source event-cluster claim comparison in
  `sourceflow/claims/comparison.py`.
- Comparison outputs article counts, claim frequency, claim polarity, entity
  focus, headline framing, evidence diversity, time-to-coverage delay, omitted
  claims, and bias findings.
- Bias detection covers omission, overemphasis, underemphasis, framing shift,
  sentiment shift, provider amplification, claim contradiction, claim
  repetition, and missing counterclaim.
- Omission is reported under `PartialCWA` with `inferred_false=False`; reports
  say `source omitted X`, not `X is false`.
- Added tests in `tests/test_phase8_source_comparison_utilities.py` and
  `sourceflow/tests/test_phase8_source_comparison.py`.

### Phase 9 - GraphRAG Retrieval

- Added BM25 chunk retrieval in `sourceflow/retrieval/bm25.py`.
- Added deterministic sparse-vector chunk retrieval in
  `sourceflow/retrieval/vector.py`.
- Added evidence pack and proof-carrying answer format in
  `sourceflow/graphrag/evidence_pack.py`.
- Added hybrid GraphRAG retriever in `sourceflow/graphrag/retriever.py`.
- Retrieval stages: parse query, detect entities, retrieve BM25 chunks,
  retrieve vector chunks, expand through KG neighbors, retrieve claims/events,
  include contradiction-linked claims, rank evidence, and return an evidence
  pack.
- Evidence packs include text chunks, claims, events, entities, graph paths,
  assumptions, citations, and provenance.
- Proof-carrying answers are not returned without evidence, keep assumptions
  explicit, do not hide contradictions, and decompose confidence into retrieval,
  extraction, and reasoning confidence.
- Added tests in `tests/test_phase9_graphrag_utilities.py` and
  `sourceflow/tests/test_phase9_graphrag.py`.

### Phase 10 - Quant 4.0 Reasoning Modules

- Added risk graph propagation in `sourceflow/quant/risk_graph.py`.
- Added auditable risk rules in `sourceflow/quant/risk_rules.yaml`.
- Risk propagation covers direct negative company events, supplier/customer KG
  relations, and portfolio exposure aggregation.
- Added event-driven alpha candidates in `sourceflow/quant/event_alpha.py` and
  `sourceflow/quant/alpha_hypotheses.py`.
- Alpha candidates include entry/exit horizons, backtest specs, source
  reliability/sector reaction reasoning, and no-live-trading assumptions.
- Added feature matrix helpers in `sourceflow/quant/features.py`.
- Added regime detector interface and rule-based baseline in
  `sourceflow/quant/regime_detector.py`.
- Regime outputs include probabilities, linked beliefs, explanations, and risk
  recomputation triggers.
- Added portfolio explanation layer in `sourceflow/quant/portfolio_explain.py`.
- Portfolio explanations include assets, positions, relevant events, risk
  factors, source evidence, graph paths, hedge candidates, confidence, and
  assumptions.
- Added tests in `tests/test_phase10_quant_utilities.py` and
  `sourceflow/tests/test_phase10_quant.py`.

### Migration Conflict Fix

- Added `monitoring/migrations/0013_merge_financial_intelligence_and_comparison.py` to merge existing `monitoring` migration leaves.
- This is an empty merge migration and should not change tables.

## Verification Passed

Run from `/home/pedro/dev/data-analysis` with `.venv/bin/python`:

- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations --check --dry-run`
- `.venv/bin/python -m unittest tests.test_phase0_architecture_contract tests.test_phase2_ingestion_utilities tests.test_phase3_entity_utilities tests.test_phase4_claim_event_utilities tests.test_phase5_kg_utilities tests.test_phase6_tms_utilities tests.test_phase7_rule_utilities tests.test_phase7_contradiction_diagnosis_utilities tests.test_phase8_source_comparison_utilities tests.test_phase9_graphrag_utilities tests.test_phase10_quant_utilities`
- `.venv/bin/python manage.py test sourceflow.tests.test_phase1_schema sourceflow.tests.test_phase2_ingestion sourceflow.tests.test_phase3_entities sourceflow.tests.test_phase4_extraction sourceflow.tests.test_phase5_kg sourceflow.tests.test_phase6_tms sourceflow.tests.test_phase7_inference_engine sourceflow.tests.test_phase7_contradictions_diagnosis sourceflow.tests.test_phase8_source_comparison sourceflow.tests.test_phase9_graphrag sourceflow.tests.test_phase10_quant`

Latest combined results: 51 dependency-light tests and 57 Django tests passed.

## Current Worktree Notes

- The worktree has uncommitted additive changes for the `sourceflow` phases, architecture docs, tests, settings registration, and the empty monitoring merge migration.
- `git diff --stat` only shows tracked-file changes because most new files are still untracked.
- Do not remove or rewrite unrelated existing project code.

## Recommended Next Steps

1. Start Phase 11: API and minimal UI exposure.
2. Add additive handlers/endpoints for evidence packs, source comparisons,
   quant risk explanations, and alpha/regime outputs.
3. Keep every API/UI response proof-carrying with provenance, assumptions,
   confidence, and reasoning path.
4. Add dependency-light utility tests and Django/API tests, then re-run the same
   verification commands plus new Phase 11 tests.

## High-Value Files

- `docs/architecture/migration_plan.md`
- `docs/architecture/module_contracts.md`
- `public_monitor/settings.py`
- `monitoring/migrations/0013_merge_financial_intelligence_and_comparison.py`
- `sourceflow/models.py`
- `sourceflow/ingestion/evidence.py`
- `sourceflow/entities/resolution.py`
- `sourceflow/claims/extractor.py`
- `sourceflow/events/extractor.py`
- `tests/test_phase4_claim_event_utilities.py`
- `sourceflow/tests/test_phase4_extraction.py`
- `sourceflow/kg/schema.py`
- `sourceflow/kg/store.py`
- `sourceflow/tests/test_phase5_kg.py`
- `sourceflow/tms/status.py`
- `sourceflow/tms/beliefs.py`
- `sourceflow/tms/retraction.py`
- `sourceflow/tests/test_phase6_tms.py`
- `sourceflow/reasoning/rules.py`
- `sourceflow/reasoning/engine.py`
- `sourceflow/reasoning/contradictions.py`
- `sourceflow/reasoning/diagnosis.py`
- `sourceflow/analysis/source_bias.py`
- `sourceflow/events/clustering.py`
- `sourceflow/claims/comparison.py`
- `sourceflow/retrieval/bm25.py`
- `sourceflow/retrieval/vector.py`
- `sourceflow/graphrag/evidence_pack.py`
- `sourceflow/graphrag/retriever.py`
- `sourceflow/quant/risk_graph.py`
- `sourceflow/quant/risk_rules.yaml`
- `sourceflow/quant/event_alpha.py`
- `sourceflow/quant/alpha_hypotheses.py`
- `sourceflow/quant/features.py`
- `sourceflow/quant/regime_detector.py`
- `sourceflow/quant/portfolio_explain.py`
- `rules/legal_event_increases_risk.yaml`
- `sourceflow/tests/test_phase7_inference_engine.py`
- `sourceflow/tests/test_phase7_contradictions_diagnosis.py`
- `sourceflow/tests/test_phase8_source_comparison.py`
- `sourceflow/tests/test_phase9_graphrag.py`
- `sourceflow/tests/test_phase10_quant.py`

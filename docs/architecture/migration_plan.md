# Migration Plan

This migration upgrades the existing public-source and quant research project
into a neurosymbolic financial reasoning system without rewriting working code.
The migration is additive, interface-first, and local-first.

## Phase 0 Gate

Implementation must begin only after these Phase 0 documents exist:

| Document | Purpose |
| --- | --- |
| `docs/architecture/current_state.md` | Audit of current repo structure, pipeline, storage, ingestion, models, UI, and API boundaries. |
| `docs/architecture/target_state.md` | Target module map and high-level architecture contract. |
| `docs/architecture/migration_plan.md` | Ordered migration path and safety constraints. |
| `docs/architecture/module_contracts.md` | Module boundary contract for later implementation. |

After the documents are present, Phase 0 may add empty `sourceflow/` package
boundaries and import tests only. No model, ingestion, reasoning, or GraphRAG
runtime behavior is added in Phase 0.

## Migration Principles

| Principle | Rule |
| --- | --- |
| Preserve working behavior | Existing Django apps, CLI commands, FastAPI endpoints, Parquet artifacts, DuckDB views, and tests remain valid. |
| Add adapters before replacements | New `sourceflow.*` modules wrap or call existing code before any replacement is considered. |
| Keep local mode first | SQLite, local filesystem, DuckDB, and local heuristics remain default. |
| Make provenance mandatory | Every extracted entity, claim, event, belief, retrieval result, and risk explanation must point back to source evidence in later phases. |
| Make assumptions explicit | OWA/CWA/PartialCWA decisions must be represented in code and data before reasoning uses them. |
| Preserve contradictions | Conflicting claims are carried into explanations instead of being collapsed or hidden. |
| Start with SQL-backed graph | Add graph interfaces and SQL tables first; RDF/Neo4j adapters are optional later. |

## Ordered Path

### Step 0 - Architecture Contract

Status: Phase 0.

Actions:

- Document the current state.
- Document the target state.
- Document migration rules.
- Document module contracts.
- Create empty package boundaries and import tests.

Exit criteria:

- Architecture docs exist.
- `sourceflow` target modules import successfully.
- No existing module is rewritten.

### Step 1 - Canonical Schema Planning

Status: implemented in Phase 1.

Actions:

- Decide whether canonical knowledge models live in an additive Django app,
  additive SQLAlchemy tables, or a bridge between both.
- Prefer reusing existing `monitoring.Source`, `Provider`, `Owner`,
  `NormalizedDocument`, `CanonicalEntity`, and `EntityAlias` where compatible.
- Add new canonical tables only for missing concepts: `DocumentChunk`,
  structured `Claim`, structured `Event`, `EvidenceSpan`, `AssumptionPolicy`,
  `Belief`, `Justification`, `InferenceRule`, `RetractionLog`,
  `RetrievalTrace`, `KnowledgeEdge`, and portfolio/risk objects not already
  covered by Quant.

Safety constraints:

- Do not mutate existing migrations destructively.
- Do not remove existing text claim or topic-cluster models.
- Add transitional adapters from existing models to canonical contracts.

Implementation status:

- Canonical knowledge models live in an additive `sourceflow` Django app.
- Existing `monitoring`, `quant`, and `researchspace` models remain unchanged.
- `sourceflow/migrations/0001_initial.py` creates canonical source, document,
  chunk, entity, claim, event, evidence, KG, assumption, belief, justification,
  retraction, retrieval, risk, asset, instrument, and portfolio tables.
- `sourceflow/reasoning/assumptions.py` provides dependency-light OWA, CWA,
  PartialCWA, unique-name, and no-unique-name policy resolution.

### Step 2 - Ingestion And Normalization Adapters

Status: implemented in Phase 2.

Actions:

- Wrap RSS/API/HTML/sitemap/PDF/local-file/finance connectors behind
  `sourceflow.ingestion`.
- Normalize all document-like records into a canonical document contract.
- Add content hashing, duplicate detection, chunking, ingestion version, and
  source metadata preservation.

Safety constraints:

- Existing ingestion commands keep their behavior.
- Adapter outputs may be additive side effects but must not replace current
  `NormalizedDocument` writes until tests prove compatibility.

Implementation status:

- `sourceflow/ingestion/dedup.py` provides canonical URL normalization,
  whitespace-stable content hashes, document dedupe keys, in-memory duplicate
  checks, and lazy DB duplicate checks.
- `sourceflow/ingestion/chunker.py` provides offset-preserving text chunking with
  bounded overlap and span-to-chunk lookup.
- `sourceflow/ingestion/normalizer.py` provides source-neutral `DocumentInput`,
  normalized document envelopes, and lazy persistence into canonical `Document`
  and `DocumentChunk` tables.
- `sourceflow/ingestion/evidence.py` provides exact evidence span extraction,
  canonical `EvidenceSpan` persistence, and helper lookups that return original
  document/chunk/span provenance for claims and supporting or contradicting
  claims for beliefs.
- Existing monitoring, Quant, QuantSpace, and `src` ingestion paths remain
  untouched.

### Step 3 - Entity Layer

Status: implemented in Phase 3.

Actions:

- Wrap existing entity extraction and alias code behind `sourceflow.entities`.
- Add provider contracts for extraction and linking.
- Add NIL candidates and merge workflow.

Safety constraints:

- Existing `CanonicalEntity` and `EntityAlias` records remain valid.
- Ticker/ISIN/LEI/CNPJ uniqueness must be scoped by the correct context.

Implementation status:

- `sourceflow/entities/extractor.py` defines `EntityExtractor`,
  `EntityMentionCandidate`, and a dependency-light heuristic extractor that
  returns mention text, span offsets, entity type, confidence, and extractor
  metadata.
- `sourceflow/entities/aliases.py` provides alias normalization, exact
  identifier normalization, alias upserts, exact alias lookup, external ID lookup,
  and canonical entity creation/update helpers.
- `sourceflow/entities/resolution.py` provides context-aware linking, exact
  ticker/ISIN/LEI/CNPJ handling, fuzzy company-name matching, NIL result support,
  and an entity merge workflow that remaps mentions, claims, events, beliefs, and
  aliases.
- `sourceflow/entities/linker.py` persists linked or NIL `EntityMention` rows with
  evidence spans and chunk provenance.

### Step 4 - Claims And Events

Status: implemented in Phase 4.

Actions:

- Add structured claim extraction and validation.
- Add actor-predicate-object event extraction and event classification.
- Attach every claim/event to evidence spans.

Safety constraints:

- Existing comparison models remain available for coverage reports.
- Incomplete claims are rejected or marked incomplete, not silently promoted to
  facts.

Implementation status:

- `sourceflow/claims/normalizer.py` provides canonical predicate, object, and
  polarity/modality normalization for structured claim candidates.
- `sourceflow/claims/validators.py` validates claim candidates before
  persistence and marks missing subject, predicate, object, evidence, or low
  confidence cases as incomplete/rejected.
- `sourceflow/claims/extractor.py` defines the extractor provider contract,
  dependency-light heuristic claim extraction, and canonical `Claim`
  persistence with subject/object entity resolution and evidence spans.
- `sourceflow/events/classifier.py` maps actor-predicate-object tuples to
  market event classes with auditable keyword rules.
- `sourceflow/events/impact_schema.py` provides default risk-channel and
  impact metadata for extracted events.
- `sourceflow/events/extractor.py` defines the event extractor provider
  contract, claim-derived event extraction, NIL-safe actor handling, and
  canonical `Event` persistence with evidence spans.
- Phase 4 tests cover dependency-light claim/event utilities and Django-backed
  claim/event persistence with provenance.

### Step 5 - Knowledge Graph

Status: implemented in Phase 5.

Actions:

- Add `GraphStore` interface.
- Implement SQL-backed graph tables first.
- Map entities, sources, documents, chunks, claims, events, risk factors,
  assets, instruments, and portfolios to graph nodes and edges.

Safety constraints:

- NetworkX research helpers remain available.
- Unknown edge types are rejected.
- Every edge carries confidence, provenance, and timestamp.

Implementation status:

- `sourceflow/kg/schema.py` provides dependency-light typed node references,
  the canonical node-type set, an auditable edge-type registry with allowed
  endpoint pairs, and edge validation that rejects unknown edge types and
  disallowed endpoint pairs.
- `sourceflow/kg/store.py` defines the `GraphStore` protocol (add_node,
  add_edge, get_neighbors, find_paths, query, upsert_claim, upsert_event) and
  a local-first `SqlGraphStore` backed by the canonical `KnowledgeEdge` table.
- Edge persistence is idempotent on (edge type, source node, target node),
  requires non-empty provenance, and stamps confidence and observation time on
  every edge.
- `upsert_claim` and `upsert_event` map canonical claims/events to
  subject/actor, object, document, source, and evidence-span edges carrying
  record provenance.
- `sourceflow/finance_graph` and other NetworkX research helpers remain
  untouched.

### Step 6 - Truth Maintenance And Reasoning

Status: Phase 6 and Phase 7 reasoning tasks are implemented.

Actions:

- Add beliefs, justifications, dependency traversal, retraction logs, and
  recomputation hooks.
- Add assumption policies and rule engine.
- Add contradiction detection and abductive diagnosis.

Safety constraints:

- News defaults to OWA.
- Internal controlled tables can use CWA.
- Contradictions mark dispute state and do not crash inference.

Implementation status:

- `sourceflow/tms/status.py` provides dependency-light truth status
  resolution: active justification weights resolve to `true_supported`,
  `partially_supported`, `false_supported`, or `contradicted`; mixed evidence
  marks a dispute and never collapses or raises; with no active evidence the
  assumption policy decides (OWA keeps unknown, CWA infers supported absence).
- `sourceflow/tms/beliefs.py` creates beliefs with mandatory provenance, a
  resolved `AssumptionPolicy` row, and at least one `Justification` row
  linking supporting/contradicting claims, events, beliefs, or rules;
  `recompute_belief` re-derives truth status from active justifications.
- `sourceflow/tms/retraction.py` retracts claims, events, and beliefs with
  `RetractionLog` audit rows, transitively marks dependent beliefs stale with
  per-belief audit rows, and `recompute_stale_beliefs` reactivates them with
  fresh truth status. Events carry no status column, so their retraction
  record is the audit row consulted by `justification_is_active`.
- Phase 6 tests cover dependency-light status resolution and Django-backed
  belief creation, retraction propagation, and recomputation.
- `sourceflow/reasoning/rules.py` parses and validates deterministic and
  defeasible YAML rules with supported rule types: deductive, default,
  abductive, diagnostic, risk propagation, source comparison, and retrieval
  expansion.
- `sourceflow/reasoning/engine.py` persists `InferenceRule` rows, applies
  matching rules to canonical support records, creates rule-derived `Belief`
  rows through the TMS, and attaches `derived_by_rule` justifications that
  reference both the rule and source support.
- Default-rule exceptions can block defeasible conclusions before beliefs are
  created.
- `rules/legal_event_increases_risk.yaml` provides the first default rule for
  negative lawsuit events increasing litigation risk unless an exception
  matches.
- Phase 7.1 tests cover dependency-light rule parsing/matching and
  Django-backed inference with rule/source-support justifications.
- `sourceflow/reasoning/contradictions.py` detects claims with the same
  subject, predicate, and object but opposite polarity; preserves both claims;
  marks them as disputed/source-disputed; and persists bidirectional
  `contradicts` graph edges with source and evidence provenance.
- The inference engine skips hard truth derivation from source-disputed claim
  support instead of failing globally or exploding into arbitrary conclusions.
- `sourceflow/reasoning/diagnosis.py` generates ranked abductive hypotheses for
  price moves, volume spikes, volatility shocks, LOB anomalies, negative news
  clusters, sector divergence, and macro events using event, claim, KG, and
  market evidence.
- Diagnosis outputs include supporting evidence, missing evidence, graph path,
  confidence, and recommended next retrieval.
- Phase 7.2 and 7.3 tests cover dependency-light contradiction/diagnosis
  utilities and Django-backed contradiction persistence, inference skipping, and
  stock-move diagnosis.

### Step 7 - Source Comparison And GraphRAG

Status: Phase 8 source comparison and Phase 9 GraphRAG implemented.

Actions:

- Extend provider/owner grouping and event coverage comparison.
- Implement BM25/vector/graph hybrid retrieval.
- Return proof-carrying evidence packs and answers.

Safety constraints:

- Omission is reported under PartialCWA.
- GraphRAG answers require evidence and must include contradictions when present.

Implementation status:

- `ProviderOwner` already exists in the canonical schema, and `Source` already
  carries owner, country/region, content type, reliability score, and bias tags.
- `sourceflow/analysis/source_bias.py` groups sources by owner, provider,
  region, ideology/business category, and content type; exposes reliability
  metadata helpers; and detects omission, over/underemphasis, framing shift,
  sentiment shift, provider amplification, claim contradiction, claim
  repetition, and missing counterclaim signals.
- `sourceflow/events/clustering.py` clusters structured events by actor, event
  type, and object, with related claims attached by document or subject.
- `sourceflow/claims/comparison.py` compares one event cluster source by source
  and returns article counts, claim frequency, polarity, entity focus, headline
  framing, evidence diversity, time-to-coverage delay, omissions, and bias
  findings.
- Omission findings are explicitly represented under `PartialCWA` with
  `inferred_false=False`; reports say `source omitted X`, not `X is false`.
- Phase 8 tests cover dependency-light grouping/comparison and Django-backed
  provider grouping, reliability metadata updates, event-cluster comparison,
  omissions, repetition, and sentiment/counterclaim shifts.
- `sourceflow/retrieval/bm25.py` implements dependency-light BM25 retrieval over
  canonical text chunks with document/source provenance.
- `sourceflow/retrieval/vector.py` implements deterministic sparse-vector
  retrieval over the same chunk interface.
- `sourceflow/graphrag/retriever.py` parses queries, detects known entities,
  retrieves BM25 and vector chunks, expands through KG neighbors, retrieves
  related claims/events, includes contradiction-linked claims, ranks evidence,
  persists `RetrievalTrace`, and returns an evidence pack.
- `sourceflow/graphrag/evidence_pack.py` defines evidence items, confidence
  decomposition, evidence packs, and proof-carrying answers.
- Proof-carrying answers are not returned without evidence; assumptions are
  explicit; contradictions are included when available; confidence is decomposed
  into retrieval, extraction, and reasoning components.
- Phase 9 tests cover dependency-light BM25/vector/evidence-pack behavior and
  Django-backed hybrid retrieval with chunks, claims, events, entities, graph
  paths, provenance, contradiction inclusion, retrieval traces, and answer
  formatting.

### Step 8 - Quant Reasoning, API/UI, Evaluation, Orchestration

Status: Phases 10 through 15 implemented (quant reasoning, API/UI, evaluation, orchestration, storage, and final integration). All 15 phases of the plan are complete; the Definition of Done is met.

Actions:

- Add risk graph, event-alpha candidates, regime detector interface, and
  portfolio explanation adapters over existing Quant services.
- Add API endpoints and minimal UI screens.
- Add gold datasets and reasoning tests.
- Add pipeline stages, job state integration, storage strategy, and end-to-end
  demo.

Safety constraints:

- No live trading or broker execution paths are introduced.
- Every conclusion must carry provenance, assumptions, confidence, and reasoning
  path.

Implementation status:

- `sourceflow/quant/risk_graph.py` propagates direct negative-event risk to
  entities/risk channels, propagates supplier/customer risk through KG edges,
  aggregates risk to portfolio exposure, and returns graph paths plus source
  evidence.
- `sourceflow/quant/risk_rules.yaml` stores auditable local risk rules for legal,
  sentiment, regulatory, and supply-chain propagation.
- `sourceflow/quant/event_alpha.py` converts reliable structured events and
  sector reactions into testable alpha candidates.
- `sourceflow/quant/alpha_hypotheses.py` defines candidate IDs, entry/exit
  horizons, backtest specs, and reasoning trails.
- `sourceflow/quant/features.py` provides a small feature-matrix adapter for
  price, volatility, liquidity, multifractal, and KG-risk features.
- `sourceflow/quant/regime_detector.py` defines the regime detector interface
  and an auditable rule-based baseline that outputs regime probabilities,
  linked beliefs, explanations, and risk-recompute triggers.
- `sourceflow/quant/portfolio_explain.py` lists top portfolio risk contributors
  with positions, relevant events, risk factors, source evidence, graph paths,
  rule-based hedge candidates, confidence, and assumptions.
- Phase 10 tests cover dependency-light quant utilities and Django-backed risk
  propagation, event alpha, regime detection, and portfolio explanations.
- `sourceflow/api/` exposes Phase 11 Task 11.1 as plain Django JSON views wired
  into the project URLconf under `/sourceflow/api/`: documents, entities,
  claims, events, kg/entity/{id}, kg/path, beliefs/{id}/explain, reasoning/run,
  graphrag/query, source-comparison/event/{id}, quant/risk/{asset_id}, and
  quant/portfolio/explain. `responses.py` gives every endpoint a typed,
  logged error envelope (stable HTTP codes + `error.type`); `serializers.py`
  attaches provenance (source/document/evidence span) to claims, events,
  beliefs, justifications, and graph edges. The API is CSRF-exempt for
  programmatic clients.
- `sourceflow/ui/` provides the Phase 11 Task 11.2 minimal screens under
  `/sourceflow/` (Django templates in `sourceflow/templates/sourceflow/`):
  document explorer, entity profile (with its claims/events), claim explorer,
  event cluster view, source comparison view, knowledge-graph path view, belief
  explanation view, GraphRAG query screen, risk graph view, and portfolio
  explanation view.
- Phase 11 tests (`tests/test_phase11_api.py`) cover every endpoint plus the
  acceptance screens: JSON responses, provenance on reasoning endpoints, typed
  errors (404/400/422/405/invalid_json), proof-carrying GraphRAG answers, and
  PartialCWA source-comparison output.
- `data/eval/` holds the Phase 12 gold dataset (`gold_documents.jsonl`,
  `gold_claims.jsonl`, `gold_events.jsonl`, 32 labeled financial/news documents)
  regenerable via `data/eval/build_gold.py`. The gold set is deliberately
  discriminating: a few items use verbs outside the heuristic pattern (missed by
  the extractor) and a few pattern sentences are unlabeled traps, so precision
  and recall land below 1.0.
- `sourceflow/evaluation/extraction_eval.py` runs the real extractors over the
  gold corpus and computes the named metrics: entity/claim/event precision and
  recall, evidence-span accuracy, and contradiction-detection accuracy. Current
  scores: entity 0.94/1.00, claim 0.94/0.94, event 0.91/0.91, evidence-span
  1.00, contradiction-detection 1.00.
- Phase 12 reasoning tests (`tests/test_phase12_reasoning.py`) assert the seven
  required behaviors: CWA not applied to news, OWA infers no falsity from missing
  news, PartialCWA detects omission, contradictions don't crash inference,
  retraction updates dependent beliefs, risk propagation yields an auditable
  graph path, and GraphRAG includes supporting and contradicting evidence.
  `tests/test_phase12_evaluation.py` asserts the metric harness runs and its
  numbers stay in discriminating bands.
- `sourceflow/orchestration/` implements the Phase 13 document pipeline: a
  13-stage registry (`stages.py`: ingest, normalize, chunk, extract_entities,
  link_entities, extract_claims, extract_events, update_kg, run_reasoning,
  update_tms, update_retrieval_index, run_quant_signals, generate_reports) over
  the real sourceflow operations; `policies.py` (RetryPolicy + token-bucket
  RateLimitPolicy); and `runner.py` (`PipelineRunner`) which creates a job,
  runs stages in order or one at a time, retries failed stages, and persists
  per-stage state. Job state lives in the `PipelineJob` and `PipelineStageRun`
  tables (migration `0003`). Stages are independently runnable, failed stages
  are retryable, state is visible via `job_state()`, and each stage logs the
  document id and the model/extractor versions it used.
- `manage.py run_pipeline` exposes the pipeline on the CLI: start a new job,
  run/retry a single stage on an existing job, or print a job's visible state.
- Phase 13 tests (`tests/test_phase13_orchestration.py`) cover full end-to-end
  runs, per-stage independence and retry, visible state, logged document id +
  model versions, the CLI, and the rate-limit policy.
- `sourceflow/storage/` implements the Phase 14 storage strategy. Transactional
  state stays in the Django ORM (SQLite/Postgres). `snapshot.py` exports curated
  canonical tables to Parquet (streamed via `.iterator()`) with a manifest whose
  per-table content hash is over the ordered, type-normalized logical rows, so
  snapshots are reproducible. `analytics.py` (`SourceflowAnalytics`) runs DuckDB
  queries over the Parquet snapshot only -- never the transactional DB -- so
  analytics cannot block ingestion, and columnar scans keep large
  document/chunk aggregates efficient. `vectors.py` provides a NumPy-backed
  `LocalVectorStore` (deterministic hashing embedder, reproducible persistence)
  with optional FAISS/Chroma backends via a factory that raises clearly when the
  library is absent. `graph_export.py` adds the optional RDF (N-Triples) export
  over `KnowledgeEdge` and a Neo4j adapter that activates only when the driver is
  installed; the SQL graph store remains the default.
- Phase 14 tests (`tests/test_phase14_storage.py`) cover snapshot
  reproducibility, analytics decoupled from the transactional store, large-table
  aggregation, vector search + persistence, RDF export, and the optional-backend
  guards.
- `sourceflow/orchestration/demo.py` (`run_end_to_end_demo`) is the Phase 15
  capstone: it composes the Phase 1-14 modules over one scenario -- a cluster of
  articles about a company facing a regulatory investigation, including a
  disputing source and an omitting source, a supplier KG relation, and a
  portfolio position -- and returns a structured report with all ten required
  outputs (documents ingested, entities linked, claims, event, source
  comparison, risk belief, supporting+contradicting evidence, risk propagation,
  GraphRAG answer, portfolio explanation) plus the Definition-of-Done invariants.
- `manage.py demo_e2e` runs the whole flow from one command (`--summary` for
  headlines + invariants; default rolls the seeded data back so it is
  repeatable). The invariants assert every belief has a justification, every
  conclusion carries evidence, the GraphRAG answer is proof-carrying, the
  contradiction is preserved rather than collapsed, and every risk path is
  auditable (graph path + source evidence).
- Phase 15 tests (`tests/test_phase15_demo.py`) assert all ten outputs, the five
  Definition-of-Done invariants, and that the demo runs from one command.

## Current-to-Target Compatibility Rules

| Existing code | Migration rule |
| --- | --- |
| `monitoring.Source`, `Provider`, `Owner` | Treat as source/provider-owner base until canonical schema proves a need for additive fields or tables. |
| `monitoring.NormalizedDocument` | Treat as current document base; add chunks and evidence spans additively. |
| `monitoring.CanonicalEntity`, `EntityAlias`, `DocumentEntity`, `ArticleEntityMention` | Treat as current entity base; add external IDs, NIL candidates, and mention offsets additively. |
| `monitoring.comparison_models.Claim` | Treat as legacy text claim; structured claims must be additive and adapter-backed. |
| `monitoring.TopicCluster` and `EventCoverage` | Treat as coverage/event-cluster inputs; structured market events are additive. |
| `sourceflow/finance_graph` and `sourceflow/intelligence/market/knowledge_graph.py` | Treat as in-memory/research graph helpers; persistent KG uses a new graph store boundary. |
| `quant` services and models | Treat as quant/risk/regime/portfolio adapter targets. Do not rewrite them for KG work. |
| `researchspace` paper retrieval | Treat as evidence-first retrieval pattern and adapter target for GraphRAG. |
| `src.api` and `src.cli` | Extend through additive handlers/subcommands when future phases need API/CLI exposure. |

## Phase 0 Acceptance Mapping

| Acceptance criterion | How this phase satisfies it |
| --- | --- |
| The current pipeline is documented. | `current_state.md` documents apps, storage, ingestion, models, graph/retrieval, and gaps. |
| The target modules are mapped to existing files. | `target_state.md` and `module_contracts.md` map each `sourceflow.*` boundary to adapter targets. |
| No implementation starts before the migration plan is written. | This file is written before empty module boundaries are added. |
| Empty module structure with `__init__.py`. | Added after architecture docs. |
| Basic unit tests proving imports work. | Added after module boundaries. |

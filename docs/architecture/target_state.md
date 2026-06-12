# Target State

The target architecture is an additive neurosymbolic financial reasoning system.
It keeps the existing Django, FastAPI, CLI, Quant4, QuantSpace, Sourceflow, and
storage contracts intact while adding explicit module boundaries for canonical
documents, entities, claims, events, graph storage, reasoning, truth maintenance,
retrieval, GraphRAG, and quant explanations.

## Target Package Boundary

```text
sourceflow/
  ingestion/
  normalization/
  entities/
  claims/
  events/
  kg/
  reasoning/
  tms/
  retrieval/
  graphrag/
  quant/
  evaluation/
  api/
```

Phase 0 creates only empty package boundaries and import tests. Later phases add
adapters and implementations behind those boundaries.

## Boundary-To-Existing-Code Map

| Target module | Existing adapter targets | Target responsibility |
| --- | --- | --- |
| `sourceflow.ingestion` | `monitoring/parsers/`, `monitoring/management/commands/ingest_*`, `sourceflow/finance_ingestion/`, `src/pipeline/ingestion/`, `quantspace/services/pdf_extraction.py` | Source-specific ingestion adapters for RSS, HTML, APIs, filings, reports, PDFs, local files, and market data. |
| `sourceflow.normalization` | `monitoring/ingestion_v2.py`, `monitoring/normalizers.py`, `sourceflow/finance_ingestion/normalization.py`, `src/pipeline/preprocessing/` | Canonical document normalization, URL canonicalization, content hashing, deduplication, text cleaning, and chunking. |
| `sourceflow.entities` | `monitoring.entities`, `monitoring.CanonicalEntity`, `EntityAlias`, `DocumentEntity`, `ArticleEntityMention`, `sourceflow/intelligence/meta_factors/entities.py` | Entity extraction provider boundary, alias registry, entity linking, NIL candidates, and merge workflows. |
| `sourceflow.claims` | `monitoring.comparison_models.Claim`, `ClaimCluster`, `ClaimClusterMember`, `sourceflow/intelligence/meta_factors/articles.py` | Structured claim extraction, claim normalization, validation, comparison, contradiction inputs, and evidence binding. |
| `sourceflow.events` | `monitoring.TopicCluster`, `DocumentTopic`, `EventCoverage`, `quant4/services/graphs/`, `sourceflow/intelligence/meta_factors/events.py` | Market-relevant actor-predicate-object events, event classification, event clustering, and impact schema. |
| `sourceflow.kg` | `sourceflow/finance_graph/`, `sourceflow/intelligence/market/knowledge_graph.py`, `quant4.GraphSnapshot`, `monitoring.EntityRelationship` | Persistent graph store abstraction, SQL-backed graph tables first, path queries, claim/event upserts, and optional later RDF/Neo4j adapters. |
| `sourceflow.reasoning` | `sourceflow/intelligence/symbolic/`, `sourceflow/intelligence/search/`, existing alert/risk rules | Assumption policies, deterministic and defeasible rules, contradiction handling, paraconsistent-safe behavior, and abductive diagnosis. |
| `sourceflow.tms` | No direct equivalent; closest patterns are `monitoring.EventComparisonSnapshot`, `quantspace.PaperCitation`, and provenance JSON fields | Beliefs, justifications, dependencies, retractions, recomputation, and stale-summary invalidation. |
| `sourceflow.retrieval` | `monitoring.ArticleEmbedding`, `quantspace/services/vector_search.py`, `src/warehouse/`, `src/storage/` | BM25/vector retrieval interfaces, claim/event/entity retrieval, and evidence ranking. |
| `sourceflow.graphrag` | `monitoring/management/commands/build_graphrag_context.py`, `sourceflow/intelligence/xai/rag_context.py`, `quantspace/services/ask_paper.py` | Hybrid graph/text retriever, evidence packs, proof-carrying answer format, citations, and contradiction inclusion. |
| `sourceflow.quant` | `quant4/services/`, `sourceflow/finance_features/`, `sourceflow/finance_models/`, `src/pipeline/evaluation/` | Risk graph, event-alpha candidates, regime detector interface, portfolio explanation, and links to existing Quant4 research services. |
| `sourceflow.evaluation` | `tests/`, `monitoring/tests/`, `quant4/tests/`, `quantspace/tests/`, `src/pipeline/evaluation/` | Gold datasets, extraction metrics, reasoning tests, retrieval tests, and end-to-end demo assertions. |
| `sourceflow.api` | `src/api/app.py`, `src/api/handlers.py`, Django URLs/views | Future API endpoint adapters for documents, entities, claims, events, KG, beliefs, reasoning, GraphRAG, source comparison, and quant explanations. |

## Target Data Flow

```text
source adapter
  -> raw payload / snapshot
  -> canonical Document
  -> DocumentChunk
  -> EntityMention candidates
  -> linked Entity / EntityAlias
  -> Claim and Event with EvidenceSpan
  -> KnowledgeEdge updates
  -> AssumptionPolicy evaluation
  -> Belief and Justification graph
  -> Retrieval indexes and GraphRAG evidence packs
  -> Risk graph, alpha candidates, regimes, and portfolio explanations
  -> API/UI/CLI/background task outputs with provenance
```

## Storage Targets

| Store | Target use | Initial backend |
| --- | --- | --- |
| Transactional DB | Sources, documents, chunks, entities, claims, events, evidence, assumptions, beliefs, justifications, graph edges, retrieval traces, risk objects | Existing SQLite by default, optional Postgres through existing runtime settings. |
| SQL graph tables | Nodes, edges, path/query support, provenance, confidence, timestamps | Additive SQL tables first. Do not require Neo4j/RDF for MVP. |
| Parquet data lake | Historical snapshots, market panels, feature matrices, evaluation datasets, backtest/risk outputs | Existing local/object-storage Parquet path. |
| DuckDB | Analytical queries over Parquet and snapshots | Existing `src.warehouse` facade. |
| Vector store | Chunk/article/paper embeddings and GraphRAG candidates | Local implementation first. Reuse existing JSON embeddings or add a provider interface before vendor-specific storage. |
| Model provider | Extraction, embeddings, summarization, optional LLMs | Provider interface first. Local heuristic and retrieval-only modes remain valid. |

## Assumption And Reasoning Targets

News, articles, source claims, and scraped documents default to open-world
assumptions. Controlled internal tables such as trades, jobs, pipeline state,
portfolio positions, and explicit holdings default to closed-world assumptions.
Source coverage comparison uses partial closed-world assumptions so omission is
reported as source omission, not as falsity of the omitted fact.

Contradictions are preserved. The system must not collapse competing source
claims into a single truth value, and contradictory claim sets must not cause
reasoning explosion. Derived beliefs must carry rule IDs, assumptions, supporting
or contradicting claims/events, confidence components, and evidence spans.

## API And UI Target

The target API/UI should be added through adapters over existing `src.api` and
Django surfaces. Required future endpoints include documents, entities, claims,
events, KG entity/path queries, belief explanation, reasoning run, GraphRAG query,
source comparison, asset risk, and portfolio explanation. Every reasoning endpoint
must return provenance and typed errors.

## Non-Goals For This Migration

| Non-goal | Reason |
| --- | --- |
| Rewriting current ingestion | Existing RSS/API/HTML/financial ingestion already works and has tests. |
| Replacing Django models in place | Existing migrations and admin/API behavior must keep working. |
| Requiring Neo4j, RDF, cloud vector DBs, or paid APIs | The project is local-first and budget-first. SQL-backed graph and local retrieval come first. |
| Treating missing news as false | News and source claims are open-world by default. |
| Returning RAG answers without evidence | Target GraphRAG answers must be proof-carrying. |

## Phase 0 Target

Phase 0 completes when the current pipeline is documented, target modules are
mapped to existing files, the migration plan is written, the empty `sourceflow/`
module boundary exists, and import tests prove the new boundaries are available
without breaking existing imports.

# Module Contracts

This file defines Phase 0 module boundaries for the Agentic Knowledge Reasoning,
GraphRAG, and Quant 4.0 migration. These are contracts for later phases, not
runtime implementations. Phase 0 package files are intentionally empty.

## Cross-Cutting Contract

Every pipeline step added in later phases must be callable from four surfaces:

| Surface | Contract |
| --- | --- |
| Python function | A pure or side-effect-explicit function under the relevant `sourceflow.*` module. |
| CLI command | A `src.cli` subcommand or Django management command that delegates to the Python function. |
| Background task | A job stage compatible with existing `PipelineJob`, `JobRunEvent`, `pipeline_runs`, or `pipeline_tasks` state. |
| Future API endpoint | A handler under `src.api` or Django view that delegates to the same Python function. |

Each callable step should accept explicit inputs and return structured result
objects or dictionaries. It must not rely on hidden global state except runtime
settings and provider registries already used by the project.

## Provider Interfaces To Add Later

These interfaces are required by the implementation plan, but they are not added
as executable code in Phase 0.

### Graph Store

```python
class GraphStore:
    def add_node(...): ...
    def add_edge(...): ...
    def get_neighbors(...): ...
    def find_paths(...): ...
    def query(...): ...
    def upsert_claim(...): ...
    def upsert_event(...): ...
```

Initial backend: SQL-backed graph tables. Optional later backends: RDFLib and
Neo4j. Every edge must include edge type, confidence, provenance, and timestamp.

### Vector Store

```python
class VectorStore:
    def upsert_document_chunk(...): ...
    def upsert_article(...): ...
    def search(...): ...
    def delete(...): ...
```

Initial backend: local/provider-neutral storage reusing existing embedding JSON
patterns where possible. Optional later backends must remain behind this boundary.

### Model Provider

```python
class ModelProvider:
    def extract_entities(...): ...
    def extract_claims(...): ...
    def extract_events(...): ...
    def embed(...): ...
    def summarize_with_evidence(...): ...
```

Initial backend: local heuristics and retrieval-only behavior. Optional LLM/NLP
providers must preserve provenance and model version metadata.

## Module Responsibilities

| Module | Responsibilities | Existing adapter targets |
| --- | --- | --- |
| `sourceflow.ingestion` | Ingest source payloads, preserve raw snapshots, return canonical ingestion envelopes, and delegate existing source-specific connectors. | `monitoring/parsers/`, `monitoring/management/commands/ingest_*`, `sourceflow/finance_ingestion/`, `src/pipeline/ingestion/`, `researchspace/services/pdf_extraction.py` |
| `sourceflow.normalization` | Canonicalize URLs, hash content, deduplicate records, clean text, split chunks, and preserve source metadata. | `monitoring/ingestion_v2.py`, `monitoring/normalizers.py`, `sourceflow/finance_ingestion/normalization.py`, `src/pipeline/preprocessing/` |
| `sourceflow.entities` | Extract mentions, link aliases, resolve canonical entities, manage NIL candidates, and support merge workflows. | `monitoring.entities`, `monitoring.CanonicalEntity`, `EntityAlias`, `DocumentEntity`, `ArticleEntityMention` |
| `sourceflow.claims` | Extract structured subject-predicate-object claims, normalize predicates, validate evidence, and support claim comparison. | `monitoring.comparison_models.Claim`, `ClaimCluster`, `ClaimClusterMember` |
| `sourceflow.events` | Extract actor-predicate-object events, classify event types, cluster related events, and expose impact schema. | `monitoring.TopicCluster`, `DocumentTopic`, `EventCoverage`, `quant/services/graphs/` |
| `sourceflow.kg` | Persist and query graph nodes/edges, upsert claims/events, retrieve neighbors and paths, and validate edge types. | `sourceflow/finance_graph/`, `sourceflow/intelligence/market/knowledge_graph.py`, `monitoring.EntityRelationship`, `quant.GraphSnapshot` |
| `sourceflow.reasoning` | Resolve assumptions, run rules, detect contradictions, handle defeasible exceptions, and generate abductive hypotheses. | `sourceflow/intelligence/symbolic/`, alert/risk rule patterns, existing tests for comparison behavior |
| `sourceflow.tms` | Create beliefs, attach justifications, traverse dependencies, log retractions, recompute stale beliefs, and invalidate stale summaries. | New boundary; adapters may use provenance patterns from `researchspace.PaperCitation` and existing metadata JSON fields. |
| `sourceflow.retrieval` | Retrieve BM25/vector chunks, entities, claims, events, and graph-linked evidence with provenance. | `monitoring.ArticleEmbedding`, `researchspace/services/vector_search.py`, `src/warehouse/`, `src/storage/` |
| `sourceflow.graphrag` | Build evidence packs, expand retrieval through KG paths, include contradictions, and format proof-carrying answers. | `monitoring/management/commands/build_graphrag_context.py`, `sourceflow/intelligence/xai/rag_context.py`, `researchspace/services/ask_paper.py` |
| `sourceflow.quant` | Propagate risk, generate event-alpha candidates, expose regime detector interface, and explain portfolio exposure. | `quant/services/`, `sourceflow/finance_features/`, `sourceflow/finance_models/`, `src/pipeline/evaluation/` |
| `sourceflow.evaluation` | Store gold datasets, calculate extraction/reasoning/retrieval metrics, and drive end-to-end acceptance tests. | `tests/`, `monitoring/tests/`, `quant/tests/`, `researchspace/tests/`, `src/pipeline/evaluation/` |
| `sourceflow.api` | Provide adapter functions for future FastAPI/Django endpoints without coupling core logic to HTTP. | `src/api/app.py`, `src/api/handlers.py`, Django URL/view modules |

## Data Contract Rules

| Object | Contract |
| --- | --- |
| Source | Must carry provider/owner, URL, type, country/language when known, reliability metadata, and timestamps. |
| Document | Must carry source, URL, title, published/ingested timestamps, raw/clean text, content hash, language, and metadata. |
| DocumentChunk | Must carry parent document, chunk index, text, offsets, token count if known, and metadata. |
| EntityMention | Must carry document/chunk, text span, offsets when available, candidate type, confidence, extractor version, and linked entity if resolved. |
| Claim | Must carry subject, predicate, object entity or literal, polarity, modality, tense/time, confidence, source, document, evidence span, status, and metadata. |
| Event | Must carry actor, predicate, object entity or literal, event type, event time, extraction time, polarity, magnitude, confidence, source, document, evidence span, and metadata. |
| EvidenceSpan | Must carry document/chunk, exact text, character offsets, extractor model/version, confidence, and timestamps. |
| Belief | Must carry belief type, SPO/literal target, truth status, confidence, assumption policy, creating rule, validity window, status, and metadata. |
| Justification | Must link beliefs to supporting or contradicting claims, events, beliefs, rules, weights, and metadata. |
| RetrievalTrace | Must record query, retrieval stages, candidate IDs, ranking scores, assumptions, citations, and model/provider versions. |

## Assumption Contract

| Policy | Default use |
| --- | --- |
| OWA | News, public articles, source claims, scraped reports, and incomplete external data. |
| CWA | Controlled internal tables such as trades, jobs, pipeline tasks, and explicit portfolio positions. |
| PartialCWA | Source coverage comparison within a defined source/event/time scope. |
| CarefulCWA, GCWA, EGCWA, ExtendedCWA | Future advanced policies only after simpler OWA/CWA behavior is tested. |
| UniqueNameAssumption | Tickers, ISINs, LEIs, and CNPJs within their valid namespace/context. |
| NoUniqueNameAssumption | Ambiguous names and unscoped aliases by default. |

## GraphRAG Answer Contract

Future GraphRAG answers must use this proof-carrying shape:

```json
{
  "answer": "...",
  "supporting_claims": [],
  "contradicting_claims": [],
  "events": [],
  "entities": [],
  "graph_paths": [],
  "assumptions_used": [],
  "confidence": 0.0,
  "confidence_components": {
    "retrieval": 0.0,
    "extraction": 0.0,
    "reasoning": 0.0
  },
  "what_would_change_this": [],
  "citations": []
}
```

No answer should be emitted without evidence. Contradictions and assumptions must
be explicit.

## Import Boundary Test Contract

Phase 0 import tests verify that each target package imports without importing
heavy optional dependencies or performing I/O. Future modules should preserve that
property by keeping optional provider imports lazy and side effects behind explicit
functions.

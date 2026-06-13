# Current State

This audit captures the repository state before the Agentic Knowledge Reasoning,
GraphRAG, and Quant 4.0 migration. The existing project is not greenfield: it is
a Django public-source monitor, a Quant research app, a QuantSpace research-paper
app, a provider-neutral FastAPI/CLI stack, and a `sourceflow` package with
finance ingestion, graph, model, feature, and symbolic-factor utilities.

## Active Applications

| Area | Current files | Notes |
| --- | --- | --- |
| Django project | `public_monitor/settings.py`, `public_monitor/urls.py` | Root web app. Uses runtime settings from `src.config.settings`. |
| Public-source monitoring | `monitoring/` | Main ingestion, normalization, source metadata, entity, claim, clustering, comparison, dashboard, and orchestration app. |
| Quant | `quant/` | Django app and services for assets, market datasets, feature artifacts, regimes, risk, graphs, LOB, portfolio, and experiments. |
| QuantSpace | `researchspace/` | Django app for research papers, chunks, citations, evidence, vector search, extraction, paper QA, and factor candidates. |
| Provider-neutral stack | `src/` | FastAPI facade, CLI, providers, orchestration, storage, DuckDB warehouse, feature pipeline, model pipeline, security, and cost controls. |
| Sourceflow | `sourceflow/` | Finance ingestion, datasets, features, graphs, models, robust stats, intelligence, symbolic factors, and XAI helpers. |

## CLI And API Boundaries

| Boundary | Current files | Current behavior |
| --- | --- | --- |
| Python CLI | `src/cli.py` | Exposes `ingest`, `preprocess`, `features`, `warehouse`, `train`, `evaluate`, `backtest`, `risk`, `pipeline`, `cost`, `compute`, and `mvp-demo`. |
| FastAPI | `src/api/app.py`, `src/api/main.py`, `src/api/handlers.py` | Exposes provider-backed JSON endpoints for runtime config, pipeline runs, ingest/preprocess/features/windows/train/evaluate/risk/model/backtest operations, assets, signals, storage, reports, and efficiency. |
| Django management commands | `monitoring/management/commands/`, `quant/management/commands/`, `researchspace/management/commands/` | Existing commands cover RSS/API/source ingestion, enrichment, clustering, comparison, graph/RAG context, finance exports, Quant experiments, market/LOB ingestion, paper ingestion, paper index building, and factor generation. |
| Django UI | `monitoring/urls.py`, `monitoring/views.py`, `monitoring/intelligence_views.py`, `researchspace/urls.py`, `researchspace/views.py` | Existing server-rendered screens and internal JSON endpoints for monitoring dashboards, digest, export rows, intelligence rows, and paper workflows. |

## Current Storage

| Storage | Current files | Current use |
| --- | --- | --- |
| SQLite | `db.sqlite3`, `public_monitor/settings.py`, Django models | Default local transactional store for Django apps and local development. |
| SQLAlchemy compatibility schema | `src/database/core_schema.py`, `alembic/` | Additive SQLite/Postgres tables for assets, market bars, LOB snapshots, features, feature runs, signals, backtests, risk runs, model artifacts, ingestion runs, pipeline runs, and tasks. |
| Parquet | `data/lake/`, `exports/`, `src/storage/artifact_store.py`, `sourceflow/finance_ingestion/parquet_export.py` | Primary analytical artifact format for raw data, features, predictions, backtests, risk reports, and exports. |
| DuckDB | `src/warehouse/duckdb_context.py`, `src/warehouse/views.py`, `src/warehouse/materialize.py` | Optional/local OLAP layer over Parquet with stable views. |
| Postgres | `docker-compose.postgres.yml`, `docker-compose.cloud-mvp.yml`, `src/providers/database/postgres.py` | Optional profile through `DB_MODE=postgres` and `DATABASE_URL` or split `POSTGRES_*` variables. Not required for local mode. |
| Local/object storage facade | `src/providers/storage/`, `src/storage/` | Local filesystem is default. S3-compatible storage is optional for cloud MVP mode. |
| Media files | `media/`, `researchspace.models.Paper.pdf_file` | Raw snapshots and uploaded research PDFs. |

## Current Ingestion Paths

| Source type | Current files | Current shape |
| --- | --- | --- |
| RSS/Atom | `monitoring/parsers/rss.py`, `monitoring/management/commands/ingest_rss.py`, `monitoring/google_news.py` | RSS and Atom feeds parse into `ParsedRecord` and downstream Django records. Google News topic sources are RSS-backed. |
| HTML pages | `monitoring/parsers/html.py`, `monitoring/fetchers/http.py`, `monitoring/fetchers/browser.py` | HTML metadata and paragraph text parsing with HTTP and optional browser fetch paths. |
| Sitemaps | `monitoring/parsers/sitemap.py` | Sitemap URLs are parsed and can feed discovery/ingestion. |
| Approved JSON APIs | `monitoring/parsers/api.py`, `monitoring/management/commands/add_arxiv_query.py` | Simple JSON API and arXiv Atom ingestion paths exist. |
| Public web reports | `sourceflow/finance_ingestion/connectors/public_web.py` | Permission-gated report ingestion envelope with source attribution and policy validation. |
| Manual/local files | `sourceflow/finance_ingestion/connectors/local_files.py`, `quant/management/commands/quant_import_bars.py`, `monitoring/management/commands/import_financial_dataset.py` | CSV, JSONL, and Parquet local imports. |
| Official financial feeds | `sourceflow/finance_ingestion/connectors/sec_edgar.py`, `fred.py`, `cftc_cot.py`, `yahoo_research.py`, matching monitoring commands | SEC EDGAR, FRED, CFTC COT, and Yahoo/research connectors exist as finance-specific ingestion surfaces. |
| Research PDFs | `researchspace/management/commands/ingest_paper_pdf.py`, `researchspace/services/pdf_extraction.py` | PDF ingestion into `Paper`, `PaperChunk`, citations, and extraction artifacts. |
| Synthetic/demo rows | `src/workflows/mvp_demo.py`, `configs/cloud_mvp.yaml` | Deterministic market rows for local MVP demos. |

## Current Core Models

| Domain | Existing models | Current gap for target system |
| --- | --- | --- |
| Sources and owners | `monitoring.Source`, `monitoring.Provider`, `monitoring.Owner` | Good base for `Source` and `ProviderOwner`; target plan needs normalized bias tags and formal owner grouping metadata. |
| Raw and normalized documents | `monitoring.RawEvent`, `monitoring.NormalizedDocument`, `monitoring.IngestedItem` | Good base for `Document`; target plan needs canonical `DocumentChunk` and exact evidence spans for all extractions. |
| Entities | `monitoring.CanonicalEntity`, `EntityAlias`, `DocumentEntity`, `ArticleEntityMention` | Good base for `Entity`, `EntityAlias`, and `EntityMention`; target plan needs external IDs, NIL candidates, exchange-aware ticker semantics, and mention offsets. |
| Claims and source comparison | `monitoring.comparison_models.Claim`, `ClaimCluster`, `ClaimClusterMember`, `EventCoverage`, `FrameFeature`, `EventComparisonSnapshot` | Good base for early claim comparison; target plan needs structured subject-predicate-object claims with polarity, modality, evidence spans, and contradiction semantics. |
| Events/clusters | `monitoring.TopicCluster`, `DocumentTopic`, `TopicClusterSlice`, `EventCoverage` | Existing topic/event clusters are coverage-oriented; target plan needs market-relevant `Event(actor, predicate, object, event_type, time, impact)` records. |
| Finance/market data | `monitoring.MarketInstrument`, `MarketBar`, `MarketTick`, `quant.Asset`, `MarketDataset`, `FeatureArtifact`, `RegimeRun`, `RiskRun`, `GraphSnapshot`, `PortfolioRun`, `ModelRun`, `BacktestRun` | Good base for assets, instruments, runs, risk, regimes, and graph snapshots; target plan needs risk graph and portfolio explanation contracts. |
| Research evidence | `researchspace.Paper`, `PaperChunk`, `PaperCitation`, `PaperQuestion`, `QuantExtraction`, `FactorCandidate` | Good provenance pattern for papers; target plan should reuse this evidence-first pattern for news and KG evidence. |
| Job state | `monitoring.PipelineJob`, `JobRunEvent`, `ResourceLock`, `WorkerHeartbeat`, `src.database.core_schema.pipeline_runs`, `pipeline_tasks` | Good base for background orchestration; target plan can add reasoning job stages later without replacing this. |

## Current Graph And Retrieval Capabilities

| Capability | Current files | Notes |
| --- | --- | --- |
| NetworkX financial graph | `sourceflow/finance_graph/graph_builder.py` | Builds directed graphs from instruments and relation records with relation type, weight, confidence, and evidence URL. |
| Market/company KG helpers | `sourceflow/intelligence/market/knowledge_graph.py` | Builds weighted company/instrument graphs and propagates exposure scores. |
| Graph features | `sourceflow/finance_graph/graph_features.py`, `quant/services/graphs/` | Existing graph feature and topology code is research-oriented, not a persistent KG store. |
| Article embeddings | `monitoring.ArticleEmbedding`, `researchspace/services/vector_search.py` | Local vector-like retrieval exists for articles/papers but is not yet a unified GraphRAG layer. |
| Existing RAG context | `monitoring/management/commands/build_graphrag_context.py`, `sourceflow/intelligence/xai/rag_context.py`, `researchspace/services/ask_paper.py` | Retrieval and explanation helpers exist, but proof-carrying GraphRAG with contradictions and KG paths is not yet formalized. |

## Current Pipeline Summary

The current public-source pipeline stores raw payloads first, normalizes parsed
records into Django models, enriches documents with entities/claims/framing,
clusters topics/events, compares source coverage, and exports artifacts. The
current quant pipeline ingests market data, writes Parquet, builds DuckDB panels,
computes features and windows, trains/evaluates local models, runs backtests and
risk reports, and records metadata in Django and optional SQLAlchemy tables.

## Main Gaps For The Target System

| Gap | Impact |
| --- | --- |
| No canonical `DocumentChunk`/`EvidenceSpan` layer for all extracted facts | Claims, events, and beliefs cannot always point to exact text offsets. |
| Claims are mostly text/cluster records, not structured SPO records | Reasoning and contradiction detection need a normalized claim schema. |
| No canonical market-relevant `Event` model | Risk graph, alpha hypotheses, and event-driven explanations need typed events. |
| No formal OWA/CWA/PartialCWA policy layer | Reasoning could incorrectly infer falsehood from missing news unless policy is explicit. |
| No TMS/RMS belief and justification graph | Derived beliefs cannot yet be invalidated through dependency traversal. |
| Graph code is mostly in-memory/research-oriented | Target GraphRAG needs a persistent SQL-backed graph store interface first. |
| No proof-carrying GraphRAG response contract | Answers must expose evidence, contradictions, assumptions, confidence, and graph paths. |

## Phase 0 Conclusion

The project already has useful ingestion, storage, entity, claim, graph, retrieval,
and quant components. The target reasoning system should be added through adapter
modules under `sourceflow/` and additive Django/SQLAlchemy models in later phases.
Existing ingestion, Django models, Quant services, QuantSpace services, CLI/API,
and Parquet/DuckDB contracts should remain working during the migration.

"""Structured content for the local quant systems cookbook."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CookbookSection:
    """One cookbook section rendered in docs and the local preview.

    Example:
        `section = research_cookbook_sections()[0]`
    """

    name: str
    purpose: str
    run_commands: tuple[str, ...]
    test_commands: tuple[str, ...]
    expected_output: str
    artifacts: tuple[str, ...]
    optional_dependency_behavior: str
    safety_notes: tuple[str, ...]
    routes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NextImprovement:
    """One prioritized follow-up for the quant research systems.

    Example:
        `item = next_improvement_groups()[0].items[0]`
    """

    title: str
    priority: str
    rationale: str


@dataclass(frozen=True, slots=True)
class NextImprovementGroup:
    """A group of cookbook follow-up work.

    Example:
        `group = next_improvement_groups()[0]`
    """

    title: str
    items: tuple[NextImprovement, ...]


GLOBAL_VALIDATION_COMMANDS = (
    r".\.venv-win\Scripts\ruff.exe check quant",
    r".\.venv-win\Scripts\python.exe manage.py check",
    r".\.venv-win\Scripts\python.exe manage.py makemigrations --check --dry-run",
    r".\.venv-win\Scripts\python.exe manage.py test quant",
    r".\.venv-win\Scripts\python.exe manage.py test",
)

LOCAL_SAFETY_BOUNDARIES = (
    "No paid API dependency",
    "No live trading",
    "Optional dependencies fail clearly",
    "No fake metrics",
)

_RESEARCHSPACE_COMMANDS = (
    r'.\.venv-win\Scripts\python.exe manage.py ingest_paper_pdf '
    r'--path paper.pdf --title "Paper"',
    r".\.venv-win\Scripts\python.exe manage.py build_paper_index --paper-id 1",
    r'.\.venv-win\Scripts\python.exe manage.py ask_paper '
    r'--paper-id 1 --question "What validation is used?"',
    r".\.venv-win\Scripts\python.exe manage.py extract_quant_methodology --paper-id 1",
    r".\.venv-win\Scripts\python.exe manage.py generate_factor_candidates "
    r"--extraction-id 1",
    r".\.venv-win\Scripts\python.exe manage.py export_researchspace_parquet --paper-id 1",
)

_QUANT_CORE_COMMANDS = (
    r".\.venv-win\Scripts\python.exe manage.py quant_register_assets "
    r"--symbol SPY --symbol QQQ --asset-type equity --exchange ARCA --currency USD",
    r".\.venv-win\Scripts\python.exe manage.py quant_ingest_prices "
    r"--name spy-local --source csv --frequency 1d --symbol SPY",
    r'.\.venv-win\Scripts\python.exe manage.py quant_prepare_windows '
    r'--dataset-id 1 --name spy-window --split-json "{}" --config-json "{}"',
)

_MARKETLAB_COMMANDS = (
    r'.\.venv-win\Scripts\python.exe manage.py marketlab_prepare_windows '
    r'--values-json "[1,2,3,4,5,6]"',
    r'.\.venv-win\Scripts\python.exe manage.py marketlab_validate_shuffles '
    r'--values-json "[1,2,3,4]"',
    r'.\.venv-win\Scripts\python.exe manage.py marketlab_detect_regimes '
    r'--values-json "[1,2,3,4]"',
    r'.\.venv-win\Scripts\python.exe manage.py marketlab_run_benchmark '
    r'--predictions-json "[1,0]" --labels-json "[1,1]" '
    r"--data-start 2024-01-01 --data-end 2024-01-02 "
    r"--split-start 2024-01-02 --split-end 2024-01-02",
)

_GRAPH_COMMANDS = (
    r'.\.venv-win\Scripts\python.exe manage.py quant_build_graphs '
    r'--series-json "{""SPY"":[1,2,3],""QQQ"":[1,2,4]}" '
    r"--window-end 2024-01-03 --builder correlation",
)

_RISK_REGIME_COMMANDS = (
    r'.\.venv-win\Scripts\python.exe manage.py quant_run_risk '
    r'--returns-json "[0.01,-0.02,0.015]" --prices-json "[100,98,101]" '
    r'--volumes-json "[1000,1200,1100]" --data-start 2024-01-01 '
    r"--data-end 2024-01-03 --split-start 2024-01-03 --split-end 2024-01-03",
    r'.\.venv-win\Scripts\python.exe manage.py quant_detect_regimes '
    r'--returns-json "[0.01,-0.02,0.015]" --prices-json "[100,98,101]" '
    r"--data-start 2024-01-01 --data-end 2024-01-03 "
    r"--split-start 2024-01-03 --split-end 2024-01-03",
)

_PORTFOLIO_COMMANDS = (
    r".\.venv-win\Scripts\python.exe manage.py quant_optimize_portfolio "
    r"--symbols AAA,BBB --optimizer equal_weight "
    r"--data-start 2024-01-01 --data-end 2024-01-31 "
    r"--split-start 2024-01-31 --split-end 2024-01-31",
)

_LOB_COMMANDS = (
    r".\.venv-win\Scripts\python.exe manage.py quant_ingest_lob "
    r"--input-path data\sample_lob.jsonl --output-dir data\quant_lob "
    r"--venue-type generic --horizon 1",
    r".\.venv-win\Scripts\python.exe manage.py quant_train_lob_model "
    r"--input-path data\sample_lob.jsonl --model naive_imbalance "
    r"--data-start 2024-01-01 --data-end 2024-01-02 "
    r"--split-start 2024-01-02 --split-end 2024-01-02",
)

_FULL_EXPERIMENT_COMMANDS = (
    r'.\.venv-win\Scripts\python.exe manage.py quant_run_full_experiment '
    r'--name "global_macro_quant_v1" '
    r"--asset-classes stocks,commodities,indices,forex,futures "
    r"--symbols SPY,QQQ,DIA,^DJI,^KS11,EURUSD,USDJPY,ES,NQ,CL,GC "
    r"--timeframes 1d,1h,1m --horizon 1 --windows walk_forward "
    r"--regimes volatility,drawdown,tda,rqa,mst,lob "
    r"--graphs correlation,mst,pmfg,leadlag_signature,imf_coherence,"
    r"dynamic_sparse,hypergraph --risk-models shrinkage,pca_factor,cvar,"
    r"liquidity,lob --models naive,ridge,tcn,gcn_gru "
    r"--portfolio-optimizers equal_weight,min_var,hrp,cvar "
    r"--backtest true --no-live-trading --dry-run",
)

_MULTIFRACTAL_COMMANDS = (
    r".\.venv-win\Scripts\python.exe manage.py quant_import_bars "
    r"--csv .\bars.csv --symbol SPY --output-root data\mf_bars",
    r".\.venv-win\Scripts\python.exe manage.py quant_compute_returns "
    r"--bars-root data\mf_bars --output-root data\mf_returns",
    r'.\.venv-win\Scripts\python.exe manage.py quant_mfdfa '
    r'--series "0.01,-0.02,0.015,-0.005"',
    r'.\.venv-win\Scripts\python.exe manage.py quant_mf_diagnostics '
    r'--series "0.01,-0.02,0.015,-0.005"',
    r'.\.venv-win\Scripts\python.exe manage.py quant_mf_features '
    r'--symbol SPY --window-id w0 --series "0.01,-0.02,0.015,-0.005"',
    r'.\.venv-win\Scripts\python.exe manage.py quant_mf_risk '
    r'--series "0.01,-0.02,0.015,-0.005"',
    r'.\.venv-win\Scripts\python.exe manage.py quant_mf_regime '
    r'--series "0.01,-0.02,0.015,-0.005"',
    r'.\.venv-win\Scripts\python.exe manage.py quant_mf_portfolio '
    r'--symbols SPY,QQQ --variances "0.02,0.04"',
    r".\.venv-win\Scripts\python.exe manage.py quant_mf_report --symbol SPY",
)

_RESEARCH_COOKBOOK_SECTIONS = (
    CookbookSection(
        "ResearchSpace",
        "Local paper ingestion, RAG, extraction, and factor-candidate research.",
        _RESEARCHSPACE_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test researchspace",),
        (
            "Paper rows, chunks, prompt previews, extractions, candidates, "
            "and Parquet chunks."
        ),
        ("SQLite Paper metadata", "local uploaded PDFs", "Parquet chunk exports"),
        "PyMuPDF, embeddings, FAISS, and LLM providers remain optional fallbacks.",
        LOCAL_SAFETY_BOUNDARIES,
        (
            "/researchspace/papers/",
            "/researchspace/papers/upload/",
            "/researchspace/factor-lab/",
        ),
    ),
    CookbookSection(
        "Quant Core",
        "Registry-first asset, dataset, and window metadata for research runs.",
        _QUANT_CORE_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test quant.tests.test_core",),
        "Assets, MarketDataset rows, and WindowArtifact metadata with provenance.",
        ("SQLite quant metadata", "shared run metadata"),
        "Missing optional registry components raise clear dependency errors.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "MarketLab",
        "Experimental quant kernel for windows, shuffles, TDA, and benchmarks.",
        _MARKETLAB_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test quant.tests.test_marketlab",),
        "WindowArtifact, GraphSnapshot, ModelRun, and benchmark diagnostics.",
        ("quant shared models", "local benchmark metadata"),
        "IMF, topology, and optimizer extras fall back or fail clearly.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "Graphs And Topology",
        "Leakage-safe graph snapshots, topology filters, and hypergraph priors.",
        _GRAPH_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test quant.tests.test_graph_lab",),
        "GraphSnapshot rows with node, edge, and adjacency artifact paths.",
        ("data/quant_graphs", "GraphSnapshot metadata"),
        "PMFG, TMFG, RMT, and Sourceflow adapters are optional and gated.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "Risk And Regime",
        "Local risk metrics, stress outputs, and no-lookahead regime labels.",
        _RISK_REGIME_COMMANDS,
        (
            r".\.venv-win\Scripts\python.exe manage.py test "
            r"quant.tests.test_risk_regime",
        ),
        "RiskRun metrics, stress reports, RegimeRun labels, and model-risk fields.",
        ("SQLite RiskRun rows", "SQLite RegimeRun rows"),
        "Optional ruptures, HMM, and TDA dependencies are skipped clearly.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "Portfolio",
        "Research-only allocation, constraints, costs, and portfolio run records.",
        _PORTFOLIO_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test quant.tests.test_portfolio",),
        "PortfolioRun rows with weights, trades, metrics, and risk report paths.",
        ("data/quant_portfolios", "SQLite PortfolioRun rows"),
        "CVXPY, Riskfolio, PyPortfolioOpt, and HRP extras fail clearly.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "LOB Microstructure",
        "Optional venue-normalized order book features, labels, and baselines.",
        _LOB_COMMANDS,
        (r".\.venv-win\Scripts\python.exe manage.py test quant.tests.test_lob_lab",),
        "LOBRun rows, normalized feature artifacts, labels, and baseline metrics.",
        ("data/quant_lob", "SQLite LOBRun rows"),
        "PyTorch DeepLOB and TCN-LOB models remain optional stubs.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "Full Experiment",
        "Safe DAG orchestration from data through explainability.",
        _FULL_EXPERIMENT_COMMANDS,
        (
            r".\.venv-win\Scripts\python.exe manage.py test "
            r"quant.tests.test_full_experiment",
        ),
        "Dry-run DAG output, Experiment status, skipped steps, and artifact paths.",
        ("SQLite Experiment rows", "local artifact paths when available"),
        (
            "Missing data and optional dependencies produce skipped steps, "
            "not fake output."
        ),
        LOCAL_SAFETY_BOUNDARIES,
    ),
    CookbookSection(
        "Multifractal",
        "MF-DFA, diagnostics, features, risk, regimes, portfolio, reports, and plots.",
        _MULTIFRACTAL_COMMANDS,
        (
            r".\.venv-win\Scripts\python.exe manage.py test "
            r"quant.tests.test_multifractal_cli",
            r".\.venv-win\Scripts\python.exe manage.py test "
            r"quant.tests.test_multifractal_quality_gates",
        ),
        "JSON summaries, Parquet feature data, markdown reports, and plot artifacts.",
        ("data/quant_multifractal", "FeatureArtifact metadata", "local plot files"),
        "scikit-learn, PyWavelets, and plotting dependencies remain optional.",
        LOCAL_SAFETY_BOUNDARIES,
    ),
)

_NEXT_IMPROVEMENT_GROUPS = (
    NextImprovementGroup(
        "Required Next",
        (
            NextImprovement(
                "Executable sample fixture pack",
                "P0",
                "CSV, PDF, and JSONL fixtures make every cookbook command runnable.",
            ),
            NextImprovement(
                "Cookbook drift checks",
                "P0",
                (
                    "Command examples should stay aligned with management "
                    "command signatures."
                ),
            ),
        ),
    ),
    NextImprovementGroup(
        "Near-Term",
        (
            NextImprovement(
                "Quant web dashboard beyond the cookbook",
                "P1",
                (
                    "Operators need run metadata views, artifact links, "
                    "and status summaries."
                ),
            ),
            NextImprovement(
                "Optional dependency status panel",
                "P1",
                (
                    "Local users need to know which optional modules are available "
                    "or skipped."
                ),
            ),
            NextImprovement(
                "Artifact cleanup and reset commands",
                "P1",
                (
                    "Repeatable local tests need a safe way to clear generated "
                    "data artifacts."
                ),
            ),
        ),
    ),
    NextImprovementGroup(
        "Research Later",
        (
            NextImprovement(
                "Full-experiment execute-mode fixture coverage",
                "P2",
                (
                    "The dry-run path is covered; execute mode needs deterministic "
                    "local fixtures."
                ),
            ),
        ),
    ),
)


def research_cookbook_sections() -> tuple[CookbookSection, ...]:
    """Return all first-class quant cookbook sections.

    Example:
        `names = [section.name for section in research_cookbook_sections()]`
    """
    return _RESEARCH_COOKBOOK_SECTIONS


def next_improvement_groups() -> tuple[NextImprovementGroup, ...]:
    """Return grouped follow-up work for the quant systems.

    Example:
        `groups = next_improvement_groups()`
    """
    return _NEXT_IMPROVEMENT_GROUPS


def global_validation_commands() -> tuple[str, ...]:
    """Return the shared validation commands for the cookbook.

    Example:
        `commands = global_validation_commands()`
    """
    return GLOBAL_VALIDATION_COMMANDS


def local_safety_boundaries() -> tuple[str, ...]:
    """Return local-first safety boundaries documented by the cookbook.

    Example:
        `boundaries = local_safety_boundaries()`
    """
    return LOCAL_SAFETY_BOUNDARIES

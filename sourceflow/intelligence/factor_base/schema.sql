CREATE TABLE IF NOT EXISTS factors (
    name TEXT PRIMARY KEY,
    slug TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    expression_json TEXT NOT NULL,
    expression_text TEXT NOT NULL DEFAULT '',
    formula_text TEXT NOT NULL,
    return_type TEXT NOT NULL DEFAULT 'numeric',
    object_level TEXT NOT NULL DEFAULT 'event',
    entity_type TEXT NOT NULL,
    value_type TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'seed',
    complexity INTEGER NOT NULL,
    max_depth INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS factor_dependencies (
    factor_name TEXT NOT NULL,
    dependency_name TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    PRIMARY KEY (factor_name, dependency_name, dependency_type)
);

CREATE TABLE IF NOT EXISTS factor_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    object_level TEXT NOT NULL DEFAULT '',
    time_window_start TEXT NOT NULL DEFAULT '',
    time_window_end TEXT NOT NULL DEFAULT '',
    as_of TEXT NOT NULL,
    parquet_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS factor_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    objective TEXT NOT NULL,
    utility REAL NOT NULL,
    stability REAL NOT NULL,
    novelty REAL NOT NULL,
    complexity INTEGER NOT NULL,
    leakage REAL NOT NULL,
    score REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS factor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_name TEXT NOT NULL,
    run_started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    output_parquet_path TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT ''
);

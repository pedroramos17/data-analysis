# Offline NLP Pipeline

CPU-first enrichment for local public-source monitoring. The pipeline runs with
deterministic fallbacks before optional models are installed, and runs fully
offline after the listed models are downloaded.

## Setup

```powershell
.\.venv\Scripts\python -m pip install -r monitoring\nlp\requirements.txt
.\.venv\Scripts\python -m spacy download en_core_web_sm
.\.venv\Scripts\python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

After that download step, the runtime path uses local model files only for
MiniLM embeddings.

## CLI

```powershell
.\.venv\Scripts\python -m monitoring.nlp.pipeline --text "OpenAI reported secure growth after a security advisory. #AI" --tasks all
.\.venv\Scripts\python manage.py nlp_pipeline --text "OpenAI reported secure growth after a security advisory. #AI" --tasks all
```

## Tasks

Supported task names are `entities`, `topics`, `sentiment`, `keywords`,
`hashtags`, `embeddings`, and `summary`. Use `all` to run every task.

The JSON response includes per-task runtime, peak memory, backend names, text
size, token count, and a stable text hash for future cost comparisons.

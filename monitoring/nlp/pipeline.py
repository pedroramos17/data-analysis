"""Offline CPU-first NLP pipeline CLI and service entrypoint."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from collections.abc import Callable, Iterable

from monitoring.nlp.embeddings import embed_text
from monitoring.nlp.entities import extract_entities
from monitoring.nlp.hashtags import extract_hashtags
from monitoring.nlp.keywords import extract_keywords, keyword_terms
from monitoring.nlp.preprocess import build_text_stats, normalize_text
from monitoring.nlp.sentiment import score_sentiment
from monitoring.nlp.summarize import summarize_text
from monitoring.nlp.topics import classify_topics

ALL_TASKS = (
    "entities",
    "topics",
    "sentiment",
    "keywords",
    "hashtags",
    "embeddings",
    "summary",
)
TASK_ALIASES = {"all": "all", "embedding": "embeddings", "summarize": "summary"}


def run_pipeline(text: str, tasks: str | Iterable[str] = "all") -> dict[str, object]:
    """Run selected NLP tasks and return a JSON-serializable payload.

    Example:
        `payload = run_pipeline("OpenAI released a report.", "all")`
    """
    normalized = normalize_text(text)
    requested_tasks = parse_tasks(tasks)
    result: dict[str, object] = _base_result(normalized, requested_tasks)
    start = time.perf_counter()
    for task_name in requested_tasks:
        _run_named_task(task_name, normalized, result)
    result["cost"]["total_ms"] = round((time.perf_counter() - start) * 1000, 3)
    result["model_versions"] = _model_versions(result)
    return result


def parse_tasks(tasks: str | Iterable[str]) -> tuple[str, ...]:
    """Normalize task arguments from CLI or dashboard forms.

    Example:
        `parse_tasks("keywords,sentiment")`
    """
    raw_tasks = _raw_task_values(tasks)
    if raw_tasks == ("all",):
        return ALL_TASKS
    parsed = tuple(_normalize_task_name(task) for task in raw_tasks)
    invalid = tuple(task for task in parsed if task not in ALL_TASKS)
    if invalid:
        raise ValueError(f"Invalid NLP task {invalid}; expected one of {ALL_TASKS}")
    return tuple(dict.fromkeys(parsed))


def main(argv: list[str] | None = None) -> int:
    """Run the module CLI and write JSON to stdout.

    Example:
        `python -m monitoring.nlp.pipeline --text "..." --tasks all`
    """
    parser = _argument_parser()
    args = parser.parse_args(argv)
    payload = run_pipeline(args.text, args.tasks)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _run_named_task(
    task_name: str,
    text: str,
    result: dict[str, object],
) -> None:
    callback = _task_callback(task_name, text, result)
    payload, cost = _timed_task(callback)
    result[task_name] = payload
    result["cost"]["tasks"][task_name] = cost


def _task_callback(
    task_name: str,
    text: str,
    result: dict[str, object],
) -> Callable[[], object]:
    callbacks: dict[str, Callable[[], object]] = {
        "entities": lambda: extract_entities(text),
        "topics": lambda: classify_topics(text),
        "sentiment": lambda: score_sentiment(text),
        "keywords": lambda: extract_keywords(text),
        "hashtags": lambda: extract_hashtags(text, _existing_keywords(result)),
        "embeddings": lambda: embed_text(text),
        "summary": lambda: summarize_text(text),
    }
    return callbacks[task_name]


def _timed_task(callback: Callable[[], object]) -> tuple[object, dict[str, object]]:
    tracemalloc.start()
    start = time.perf_counter()
    try:
        payload = callback()
        status = "ok"
        error = ""
    except Exception as task_error:
        payload = {"error": str(task_error)}
        status = "error"
        error = str(task_error)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return payload, _cost_payload(start, peak, status, error)


def _cost_payload(
    start: float,
    peak: int,
    status: str,
    error: str,
) -> dict[str, object]:
    elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
    peak_kb = round(peak / 1024, 3)
    return {
        "runtime_ms": elapsed_ms,
        "memory_peak_kb": peak_kb,
        "status": status,
        "error": error,
    }


def _base_result(text: str, tasks: tuple[str, ...]) -> dict[str, object]:
    stats = build_text_stats(text)
    return {
        "text": {
            "hash": stats.text_hash,
            "length": stats.text_length,
            "tokens": stats.token_count,
            "sentences": stats.sentence_count,
        },
        "tasks": list(tasks),
        "cost": {"total_ms": 0.0, "tasks": {}},
    }


def _model_versions(result: dict[str, object]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for task_name in ALL_TASKS:
        payload = result.get(task_name)
        if isinstance(payload, dict) and "backend" in payload:
            versions[task_name] = str(payload["backend"])
    return versions


def _existing_keywords(result: dict[str, object]) -> tuple[str, ...]:
    if "keywords" in result:
        return keyword_terms(result["keywords"])
    return ()


def _raw_task_values(tasks: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(tasks, str):
        values = tuple(part.strip() for part in tasks.split(",") if part.strip())
        return values or ("all",)
    return tuple(str(task).strip() for task in tasks if str(task).strip())


def _normalize_task_name(task_name: str) -> str:
    lowered = task_name.lower().replace("-", "_")
    return TASK_ALIASES.get(lowered, lowered)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline NLP tasks.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--tasks", default="all")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

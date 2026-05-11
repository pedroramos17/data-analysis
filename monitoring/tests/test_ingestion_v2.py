from monitoring.ingestion_v2 import build_dedupe_hash, canonicalize_url, normalize_bar, normalize_tick


def test_canonicalize_url_strips_tracking_params():
    value = canonicalize_url("HTTPS://Example.com/a/?utm_source=x&x=1#frag")
    assert value == "https://example.com/a?x=1"


def test_build_dedupe_hash_prefers_url():
    a = build_dedupe_hash({"source_id": "s", "canonical_url": "https://a.com"})
    b = build_dedupe_hash({"source_id": "s", "canonical_url": "https://a.com", "external_id": "x"})
    assert a == b


def test_normalize_tick_computes_dollar_volume():
    tick = normalize_tick({"timestamp": "2026-01-01T00:00:00Z", "price": 2, "volume": 3}, "s", "AAPL", "NASDAQ")
    assert tick.dollar_volume == 6
    assert tick.quality_flags["dollar_volume_source"] == "computed"


def test_normalize_bar_computes_dollar_volume():
    bar = normalize_bar({"timestamp": "2026-01-01T00:00:00Z", "close": 5, "volume": 4}, "s", "AAPL", "NASDAQ", "1d")
    assert bar.dollar_volume == 20

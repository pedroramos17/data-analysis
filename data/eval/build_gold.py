"""Build the Phase 12 gold evaluation dataset.

The gold set is authored as structured Python and emitted to JSONL so that:

* evidence spans are exact -- each labeled claim/event's ``evidence_text`` IS one
  of the document's sentences, and the document text is the sentences joined, so
  the span is always a verbatim substring (no hand-counted offsets);
* the metrics are *discriminating* rather than trivially perfect -- some gold
  items use verbs outside the heuristic extractor's pattern set (the extractor
  misses them -> recall < 1), and a few pattern-matching sentences are left
  unlabeled as traps (the extractor over-produces -> precision < 1);
* contradictions and omissions are expressible -- within a cluster two sources
  can assert the same fact with opposite polarity (contradiction), or one source
  can omit a fact the others assert (omission under PartialCWA).

Run with the repo's Python to regenerate the JSONL deliverables:

    python data/eval/build_gold.py

Outputs (next to this file): gold_documents.jsonl, gold_claims.jsonl,
gold_events.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path

# Pattern verbs the heuristic claim extractor recognises (claims/extractor.py).
# Gold items using these are "extractable"; items using other verbs are not.
PATTERN_VERBS = {
    "faces", "reports", "signals", "denies", "confirms", "alleges", "expects",
    "forecasts", "announces", "launches", "cuts", "raises", "settles", "sues",
    "acquires", "warns", "delays",
}


def L(subject, predicate, obj, polarity, event_type):
    """A labeled sentence: produces one gold claim and one gold event."""
    return {
        "label": {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "polarity": polarity,
            "event_type": event_type,
        },
        "text": f"{subject} {predicate} {obj}.",
    }


def F(text):
    """An unlabeled (filler / trap) sentence."""
    return {"label": None, "text": text}


# --------------------------------------------------------------------------- #
# Documents. cluster_id groups docs about the same market event so the harness
# can reason about contradictions (same fact, opposite polarity across sources)
# and omissions (a source in the cluster that does not assert a shared fact).
# --------------------------------------------------------------------------- #

DOCUMENTS = [
    # c01 -- Petrobras regulatory probe; Wire vs Regional, Regional omits.
    dict(doc_id="d01", cluster="c01", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["business"], title="Petrobras under regulatory probe",
         sentences=[L("Petrobras", "faces", "a regulatory investigation", "negative", "regulatory_action"),
                    F("The probe was opened in Brazil this week.")]),
    dict(doc_id="d02", cluster="c01", source="Regional Daily", owner="Regional Co", reliability=0.70,
         bias_tags=["regional"], title="Petrobras output steady",
         sentences=[L("Petrobras", "reports", "stable production", "positive", "earnings"),
                    F("Local operations continued without interruption.")]),
    dict(doc_id="d03", cluster="c01", source="Wire B", owner="Wire Co", reliability=0.88,
         bias_tags=["business"], title="Petrobras probe widens",
         sentences=[L("Petrobras", "faces", "a regulatory investigation", "negative", "regulatory_action"),
                    F("Regulators requested additional documents.")]),

    # c02 -- Vale lawsuit; contradiction pair: same fact, opposite polarity/stance
    # across two sources (this is what the detector keys on: subject+predicate+
    # object identical, polarity opposite).
    dict(doc_id="d04", cluster="c02", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["business"], title="Vale faces lawsuit",
         sentences=[L("Vale", "faces", "a lawsuit", "negative", "lawsuit"),
                    F("Claimants are seeking damages over the dam incident.")]),
    dict(doc_id="d05", cluster="c02", source="Corporate Wire", owner="Vale IR", reliability=0.55,
         bias_tags=["corporate"], title="Vale downplays claim",
         sentences=[L("Vale", "faces", "a lawsuit", "positive", "lawsuit"),
                    F("The company called the exposure immaterial.")]),

    # c03 -- Fed macro guidance.
    dict(doc_id="d06", cluster="c03", source="Wire A", owner="Wire Co", reliability=0.92,
         bias_tags=["macro"], title="Fed signals rate path",
         sentences=[L("Fed", "signals", "a rate cut delay", "negative", "macro_event"),
                    F("Markets repriced expectations after the remarks.")]),
    dict(doc_id="d07", cluster="c03", source="Macro Times", owner="Macro Co", reliability=0.80,
         bias_tags=["macro"], title="Fed outlook",
         sentences=[L("Fed", "warns", "of sticky inflation", "negative", "macro_event")]),

    # c04 -- Apple product launch.
    dict(doc_id="d08", cluster="c04", source="Tech Wire", owner="Tech Co", reliability=0.85,
         bias_tags=["tech"], title="Apple unveils device",
         sentences=[L("Apple", "launches", "a new product", "positive", "product_launch"),
                    F("Pre-orders begin next week.")]),
    dict(doc_id="d09", cluster="c04", source="Gadget Daily", owner="Gadget Co", reliability=0.65,
         bias_tags=["tech"], title="Apple keynote recap",
         sentences=[L("Apple", "announces", "a new product", "positive", "product_launch")]),

    # c05 -- Nvidia guidance; contradiction pair (same fact, opposite polarity).
    dict(doc_id="d10", cluster="c05", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["tech"], title="Nvidia lifts guidance",
         sentences=[L("Nvidia", "raises", "guidance", "positive", "guidance"),
                    F("Demand for accelerators remained strong.")]),
    dict(doc_id="d11", cluster="c05", source="Bear Letter", owner="Bear Co", reliability=0.50,
         bias_tags=["opinion"], title="Nvidia guidance doubt",
         sentences=[L("Nvidia", "raises", "guidance", "negative", "guidance")]),

    # c06 -- Tesla executive change + recall (hard item, non-pattern verb).
    dict(doc_id="d12", cluster="c06", source="Auto Wire", owner="Auto Co", reliability=0.82,
         bias_tags=["auto"], title="Tesla CFO steps down",
         sentences=[L("Tesla", "confirms", "a cfo change", "negative", "executive_change"),
                    # hard: "recalled" is not a pattern verb -> extractor misses this gold claim
                    {"label": {"subject": "Tesla", "predicate": "recalled",
                               "object": "vehicles", "polarity": "negative",
                               "event_type": "other"},
                     "text": "Tesla recalled thousands of vehicles."}]),

    # c07 -- Boeing supply chain.
    dict(doc_id="d13", cluster="c07", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["industrial"], title="Boeing supplier issue",
         sentences=[L("Boeing", "warns", "of supplier shortage", "negative", "supply_chain_disruption"),
                    F("Deliveries may slip into next quarter.")]),

    # c08 -- Pfizer analyst revision + trap (unlabeled pattern sentence).
    dict(doc_id="d14", cluster="c08", source="Health Wire", owner="Health Co", reliability=0.84,
         bias_tags=["health"], title="Pfizer target cut",
         sentences=[L("Pfizer", "cuts", "its price target outlook", "negative", "analyst_revision"),
                    # trap: matches the pattern ("Analysts expects ...") but is NOT a gold
                    # market claim -> extractor produces it -> precision < 1
                    F("Analysts expects more volatility into the print.")]),

    # c09 -- JPMorgan credit event.
    dict(doc_id="d15", cluster="c09", source="Wire A", owner="Wire Co", reliability=0.91,
         bias_tags=["financials"], title="JPMorgan flags credit",
         sentences=[L("JPMorgan", "warns", "of credit downgrade risk", "negative", "credit_event")]),

    # c10 -- Shell M&A; contradiction pair (same fact, opposite polarity).
    dict(doc_id="d16", cluster="c10", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["energy"], title="Shell deal talk",
         sentences=[L("Shell", "confirms", "an acquisition", "positive", "merger_acquisition")]),
    dict(doc_id="d17", cluster="c10", source="Corporate Wire", owner="Shell IR", reliability=0.55,
         bias_tags=["corporate"], title="Shell deal denied",
         sentences=[L("Shell", "confirms", "an acquisition", "negative", "merger_acquisition")]),

    # c11 -- Microsoft earnings (clean positive).
    dict(doc_id="d18", cluster="c11", source="Tech Wire", owner="Tech Co", reliability=0.86,
         bias_tags=["tech"], title="Microsoft beats",
         sentences=[L("Microsoft", "reports", "record revenue", "positive", "earnings"),
                    F("Cloud growth led the quarter.")]),

    # c12 -- Amazon guidance.
    dict(doc_id="d19", cluster="c12", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["tech"], title="Amazon outlook",
         sentences=[L("Amazon", "forecasts", "softer holiday sales", "negative", "guidance")]),

    # c13 -- Vale commodity shock + hard item.
    dict(doc_id="d20", cluster="c13", source="Commodity Wire", owner="Commodity Co", reliability=0.83,
         bias_tags=["commodity"], title="Iron ore slides",
         sentences=[L("Vale", "warns", "of falling iron ore prices", "negative", "commodity_shock"),
                    {"label": {"subject": "Vale", "predicate": "halted",
                               "object": "shipments", "polarity": "negative",
                               "event_type": "other"},
                     "text": "Vale halted some shipments amid weak demand."}]),

    # c14 -- Petrobras settles (lawsuit resolution).
    dict(doc_id="d21", cluster="c14", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["business"], title="Petrobras settles case",
         sentences=[L("Petrobras", "settles", "a lawsuit", "positive", "lawsuit")]),

    # c15 -- Tesla product launch + insider.
    dict(doc_id="d22", cluster="c15", source="Auto Wire", owner="Auto Co", reliability=0.82,
         bias_tags=["auto"], title="Tesla new model",
         sentences=[L("Tesla", "launches", "a new product", "positive", "product_launch"),
                    L("Tesla", "announces", "a buyback", "positive", "insider_transaction")]),

    # c16 -- Apple supply chain warning (single source).
    dict(doc_id="d23", cluster="c16", source="Tech Wire", owner="Tech Co", reliability=0.85,
         bias_tags=["tech"], title="Apple supplier risk",
         sentences=[L("Apple", "warns", "of a supplier disruption", "negative", "supply_chain_disruption")]),

    # c17 -- Nvidia analyst upgrade.
    dict(doc_id="d24", cluster="c17", source="Street Wire", owner="Street Co", reliability=0.78,
         bias_tags=["tech"], title="Nvidia upgraded",
         sentences=[L("Nvidia", "confirms", "an analyst upgrade", "positive", "analyst_revision")]),

    # c18 -- Boeing lawsuit.
    dict(doc_id="d25", cluster="c18", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["industrial"], title="Boeing sued",
         sentences=[L("Boeing", "sues", "a parts maker", "negative", "lawsuit")]),

    # c19 -- JPMorgan earnings (positive) + filler.
    dict(doc_id="d26", cluster="c19", source="Wire A", owner="Wire Co", reliability=0.91,
         bias_tags=["financials"], title="JPMorgan profit",
         sentences=[L("JPMorgan", "reports", "higher profit", "positive", "earnings"),
                    F("Net interest income rose year over year.")]),

    # c20 -- Shell currency exposure.
    dict(doc_id="d27", cluster="c20", source="Macro Times", owner="Macro Co", reliability=0.80,
         bias_tags=["energy"], title="Shell FX hit",
         sentences=[L("Shell", "warns", "of currency headwinds", "negative", "currency_shock")]),

    # c21 -- Pfizer launch (positive).
    dict(doc_id="d28", cluster="c21", source="Health Wire", owner="Health Co", reliability=0.84,
         bias_tags=["health"], title="Pfizer drug approved",
         sentences=[L("Pfizer", "launches", "a new product", "positive", "product_launch")]),

    # c22 -- Microsoft acquisition.
    dict(doc_id="d29", cluster="c22", source="Tech Wire", owner="Tech Co", reliability=0.86,
         bias_tags=["tech"], title="Microsoft buys studio",
         sentences=[L("Microsoft", "acquires", "a studio", "positive", "merger_acquisition")]),

    # c23 -- Amazon executive change + trap.
    dict(doc_id="d30", cluster="c23", source="Wire A", owner="Wire Co", reliability=0.90,
         bias_tags=["tech"], title="Amazon exec exit",
         sentences=[L("Amazon", "confirms", "an executive change", "negative", "executive_change"),
                    F("Investors expects a smooth transition overall.")]),

    # c24 -- Tesla macro/rates sensitivity.
    dict(doc_id="d31", cluster="c24", source="Macro Times", owner="Macro Co", reliability=0.80,
         bias_tags=["auto"], title="Tesla rate sensitivity",
         sentences=[L("Tesla", "warns", "of higher rates pressure", "negative", "macro_event")]),

    # c25 -- Vale earnings (positive) closing clean case.
    dict(doc_id="d32", cluster="c25", source="Commodity Wire", owner="Commodity Co", reliability=0.83,
         bias_tags=["commodity"], title="Vale profit rises",
         sentences=[L("Vale", "reports", "higher profit", "positive", "earnings")]),
]


def build():
    documents, claims, events = [], [], []
    for doc in DOCUMENTS:
        text = " ".join(s["text"] for s in doc["sentences"])
        entities: list[str] = []
        for index, sentence in enumerate(doc["sentences"]):
            label = sentence["label"]
            if not label:
                continue
            gid = f"{doc['doc_id']}-{index}"
            if label["subject"] not in entities:
                entities.append(label["subject"])
            claims.append({
                "claim_id": gid,
                "doc_id": doc["doc_id"],
                "subject": label["subject"],
                "predicate": label["predicate"],
                "object": label["object"],
                "polarity": label["polarity"],
                "modality": "asserted",
                "evidence_text": sentence["text"],
                "extractable": label["predicate"] in PATTERN_VERBS,
            })
            events.append({
                "event_id": gid,
                "doc_id": doc["doc_id"],
                "actor": label["subject"],
                "predicate": label["predicate"],
                "object": label["object"],
                "event_type": label["event_type"],
                "polarity": label["polarity"],
                "evidence_text": sentence["text"],
                "extractable": label["predicate"] in PATTERN_VERBS,
            })
        documents.append({
            "doc_id": doc["doc_id"],
            "cluster_id": doc["cluster"],
            "source": doc["source"],
            "owner": doc["owner"],
            "url": f"https://example.test/{doc['doc_id']}",
            "title": doc["title"],
            "published_at": "2026-01-05T09:00:00+00:00",
            "language": "en",
            "reliability_score": doc["reliability"],
            "bias_tags": doc["bias_tags"],
            "text": text,
            "entities": [{"name": name, "type": "Company"} for name in entities],
        })
    return documents, claims, events


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    here = Path(__file__).resolve().parent
    documents, claims, events = build()
    _write(here / "gold_documents.jsonl", documents)
    _write(here / "gold_claims.jsonl", claims)
    _write(here / "gold_events.jsonl", events)
    print(f"wrote {len(documents)} documents, {len(claims)} claims, {len(events)} events to {here}")


if __name__ == "__main__":
    main()

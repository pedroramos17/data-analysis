# Alert Pipeline

`alert_engine.py` treats normalized documents as raw evidence, groups exact
duplicates with cheap local hashes, reads active topic clusters as event
clusters, and materializes `AlertHit` rows from either explicit `AlertRule`
matches or automatic `AlertDetector` configs.

The pipeline is deliberately CPU-cheap and offline:

- `NormalizedDocument` is evidence.
- `DedupeGroup` tracks exact duplicate baselines.
- `TopicCluster` acts as the current event cluster model.
- `DocumentTopic` maps evidence documents into a cluster.
- `AlertHit` is generated output, not a manual data-entry object.
- `AlertHitDocument` stores the evidence set for review.
- `AlertFeedback` stores human-in-loop labels for later ranking work.

Run it with:

```powershell
.\.venv\Scripts\python manage.py generate_alert_hits --since-hours 24
```

# Feature Flags

Feature defaults live in `sourceflow/config/default_flags.py`. Resolution order is Django settings override, environment variable, SQLite override, then code default.

Environment variables use `SOURCEFLOW_FLAG_<FLAG_NAME>`, for example:

```bash
SOURCEFLOW_FLAG_FIN_MODEL_GNN=true
```

SQLite overrides use:

```bash
python manage.py list_feature_flags
python manage.py set_feature_flag FIN_MODEL_GNN true
```

Disabled heavy or experimental features raise `FeatureDisabledError`.

# Model Registry Architecture

The model registry boundary stores model artifacts and metadata without coupling
forecast code to local or cloud storage.

## Providers

| `MODEL_PROVIDER` | Provider | Use case |
| --- | --- | --- |
| `local` | `LocalModelRegistryProvider` | Default local artifacts under `MODEL_CACHE_DIR` |
| `s3` / `r2` | `ObjectStoreModelRegistryProvider` | Model artifacts in configured object storage |
| `huggingface` | `HuggingFaceModelRegistryStub` | Explicit future boundary; fails clearly until implemented |

## Artifact Record

Model registry saves return metadata like:

```json
{
  "name": "naive_return_baseline",
  "version": "mvp_v1",
  "artifact_uri": "file:///.../model.json",
  "metadata": {"model_type": "baseline"},
  "provider": "local"
}
```

The compatibility database can also store model artifact metadata in the
`model_artifacts` table through `register_model_artifact()`.

## Model Factories

`build_default_model_registry()` registers CPU-first baselines, local-checkpoint
pretrained adapters, and SAMBA forecast wrappers. Heavy pretrained libraries and
PyTorch are optional and imported lazily.

## Operational Rules

- Keep local model cache as the default.
- Do not download remote pretrained models by default.
- Store external artifacts through providers, not direct SDK imports.
- Keep model metadata JSON-safe so API, CLI, and manifests can render it.

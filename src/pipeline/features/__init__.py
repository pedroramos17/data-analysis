"""DuckDB/Parquet feature extraction pipeline."""

from src.pipeline.features.runner import FeaturePipelineResult, run_feature_pipeline

__all__ = ["FeaturePipelineResult", "run_feature_pipeline"]

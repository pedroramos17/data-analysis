"""Phase 6 sliding-window dataset builder."""

from src.pipeline.windows.dataset_builder import (
    DatasetBuildResult,
    DatasetWindowOutput,
    build_dataset,
    inspect_dataset,
)
from src.pipeline.windows.diagnostics import (
    WindowDiagnostics,
    diagnose_all_windows,
    diagnose_window,
)
from src.pipeline.windows.embargo import (
    apply_embargo,
    check_embargo_violation,
    embargo_range,
    purge_overlap,
)
from src.pipeline.windows.purged_cv import (
    PurgedFoldResult,
    purged_kfold_split,
    purged_kfold_windows,
)
from src.pipeline.windows.splitter import WindowSpec, split_windows

__all__ = [
    "WindowSpec",
    "split_windows",
    "DatasetBuildResult",
    "DatasetWindowOutput",
    "build_dataset",
    "inspect_dataset",
    "WindowDiagnostics",
    "diagnose_window",
    "diagnose_all_windows",
    "embargo_range",
    "purge_overlap",
    "check_embargo_violation",
    "apply_embargo",
    "PurgedFoldResult",
    "purged_kfold_split",
    "purged_kfold_windows",
]

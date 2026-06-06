"""Phase 8 testing, validation, and backtesting pipeline."""

from src.pipeline.evaluation.backtester import BacktestResult, run_backtest_from_predictions, run_simple_backtest
from src.pipeline.evaluation.evaluator import EvaluationComparison, aggregate_metrics, evaluate_predictions
from src.pipeline.evaluation.predictor import PredictionOutput, predict_window
from src.pipeline.evaluation.risk_report import RiskReport, compute_risk_report
from src.pipeline.evaluation.runner import EvaluationPipelineResult, run_backtest_from_config, run_evaluation
from src.pipeline.evaluation.window_report import write_aggregate_report, write_window_report

__all__ = [
    "PredictionOutput",
    "predict_window",
    "EvaluationComparison",
    "evaluate_predictions",
    "aggregate_metrics",
    "BacktestResult",
    "run_simple_backtest",
    "run_backtest_from_predictions",
    "RiskReport",
    "compute_risk_report",
    "EvaluationPipelineResult",
    "run_evaluation",
    "run_backtest_from_config",
    "write_window_report",
    "write_aggregate_report",
]

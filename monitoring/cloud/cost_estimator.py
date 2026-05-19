"""Provider-neutral estimated cloud cost helpers."""

from collections.abc import Mapping
from decimal import Decimal

from monitoring.dashboard_models import DashboardSetting


DEFAULT_PROVIDER_RATES = {
    "provider_neutral": Decimal("0.50"),
    "local_runner": Decimal("0.00"),
    "kaggle_notebook": Decimal("0.00"),
    "colab": Decimal("0.00"),
    "gcp": Decimal("0.75"),
    "aws": Decimal("0.75"),
    "azure": Decimal("0.75"),
}


def estimate_cloud_job_cost(
    job_spec: Mapping[str, object],
    provider: str,
    resources: Mapping[str, object],
    runtime_hours: float,
) -> Decimal:
    """Estimate one cloud job cost without provider billing APIs.

    Example:
        `estimate_cloud_job_cost(spec, "gcp", resources, 2.0)`
    """
    rate = _provider_rate(provider)
    multiplier = _gpu_multiplier(resources)
    hours = Decimal(str(max(runtime_hours, 0)))
    partition_count = Decimal(str(_partition_count(job_spec)))
    return (rate * multiplier * hours * partition_count).quantize(Decimal("0.0001"))


def _provider_rate(provider: str) -> Decimal:
    override_rates = _setting_rates()
    if provider in override_rates:
        return Decimal(str(override_rates[provider]))
    return DEFAULT_PROVIDER_RATES.get(provider, DEFAULT_PROVIDER_RATES["provider_neutral"])


def _setting_rates() -> dict[str, object]:
    setting = DashboardSetting.objects.filter(key="cloud.cost_rates").first()
    if setting is None:
        return {}
    if isinstance(setting.value_json, dict):
        return setting.value_json
    return {}


def _gpu_multiplier(resources: Mapping[str, object]) -> Decimal:
    gpu_value = str(resources.get("gpu", ""))
    min_vram_gb = Decimal(str(resources.get("min_vram_gb", 0) or 0))
    if not gpu_value or gpu_value == "none":
        return Decimal("1")
    if min_vram_gb >= Decimal("16"):
        return Decimal("3")
    if min_vram_gb >= Decimal("8"):
        return Decimal("2")
    return Decimal("1.5")


def _partition_count(job_spec: Mapping[str, object]) -> int:
    partitions = job_spec.get("partitions", [])
    if isinstance(partitions, list) and partitions:
        return len(partitions)
    return 1

"""Financial intelligence models for Sourceflow."""

from __future__ import annotations

from django.db import models


class FeatureFlagSetting(models.Model):
    """SQLite override for a Sourceflow feature flag."""

    name = models.CharField(max_length=80, unique=True)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        """Return the CLI flag representation."""
        return f"{self.name}={str(self.enabled).lower()}"


class FinancialInstrument(models.Model):
    """Tradable or reference financial instrument metadata."""

    symbol = models.CharField(max_length=64)
    exchange = models.CharField(max_length=64, blank=True)
    mic = models.CharField(max_length=16, blank=True)
    asset_class = models.CharField(max_length=64)
    instrument_type = models.CharField(max_length=64)
    currency = models.CharField(max_length=16, blank=True)
    country = models.CharField(max_length=80, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    sector = models.CharField(max_length=128, blank=True)
    industry = models.CharField(max_length=128, blank=True)
    isin = models.CharField(max_length=32, blank=True)
    cusip = models.CharField(max_length=32, blank=True)
    figi = models.CharField(max_length=64, blank=True)
    contract_specs_json = models.JSONField(default=dict, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange", "instrument_type"],
                name="uniq_financial_instrument_identity",
            )
        ]
        indexes = [models.Index(fields=["symbol", "exchange", "active"])]

    def __str__(self) -> str:
        """Return the canonical instrument label."""
        return f"{self.symbol}:{self.exchange or self.instrument_type}"


class MarketSessionWindow(models.Model):
    """Static exchange trading-session window."""

    exchange = models.CharField(max_length=64)
    mic = models.CharField(max_length=16, blank=True)
    timezone = models.CharField(max_length=64)
    open_time = models.TimeField()
    close_time = models.TimeField()
    session_type = models.CharField(max_length=32, default="regular")
    holiday_calendar_json = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "session_type"],
                name="uniq_market_session_window",
            )
        ]

    def __str__(self) -> str:
        """Return the exchange session label."""
        return f"{self.exchange}:{self.session_type}"


class FinancialDataSource(models.Model):
    """Licensed, official, or explicitly permitted financial source."""

    name = models.CharField(max_length=180, unique=True)
    source_type = models.CharField(max_length=64)
    base_url = models.URLField(max_length=1200, blank=True)
    license_type = models.CharField(max_length=80, blank=True)
    requires_key = models.BooleanField(default=False)
    terms_url = models.URLField(max_length=1200, blank=True)
    robots_required = models.BooleanField(default=False)
    rate_limit_per_minute = models.PositiveIntegerField(default=60)
    enabled = models.BooleanField(default=True)
    compliance_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["source_type", "enabled"])]

    def __str__(self) -> str:
        """Return the source name used in commands."""
        return self.name


class OptionContract(models.Model):
    """Option contract metadata."""

    underlying = models.ForeignKey(FinancialInstrument, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=96, unique=True)
    expiration = models.DateField()
    strike = models.DecimalField(max_digits=18, decimal_places=6)
    option_type = models.CharField(max_length=8)
    exercise_style = models.CharField(max_length=32, blank=True)
    multiplier = models.DecimalField(max_digits=18, decimal_places=6, default=100)
    currency = models.CharField(max_length=16, blank=True)
    exchange = models.CharField(max_length=64, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the option contract symbol."""
        return self.symbol


class OptionSnapshot(models.Model):
    """Point-in-time option market and greek snapshot."""

    contract = models.ForeignKey(OptionContract, on_delete=models.CASCADE)
    source = models.ForeignKey(FinancialDataSource, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    bid = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    ask = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    last = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    volume = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    open_interest = models.DecimalField(
        max_digits=24, decimal_places=6, null=True, blank=True
    )
    implied_volatility = models.FloatField(null=True, blank=True)
    delta = models.FloatField(null=True, blank=True)
    gamma = models.FloatField(null=True, blank=True)
    theta = models.FloatField(null=True, blank=True)
    vega = models.FloatField(null=True, blank=True)
    rho = models.FloatField(null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "source", "timestamp"],
                name="uniq_option_snapshot",
            )
        ]

    def __str__(self) -> str:
        """Return the option snapshot label."""
        return f"{self.contract_id}:{self.timestamp.isoformat()}"


class FuturesContract(models.Model):
    """Futures contract metadata."""

    root_symbol = models.CharField(max_length=32)
    contract_symbol = models.CharField(max_length=64, unique=True)
    expiration = models.DateField(null=True, blank=True)
    exchange = models.CharField(max_length=64, blank=True)
    commodity_group = models.CharField(max_length=80, blank=True)
    multiplier = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    tick_size = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    currency = models.CharField(max_length=16, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the futures contract symbol."""
        return self.contract_symbol


class FuturesSnapshot(models.Model):
    """Point-in-time futures bar or settlement snapshot."""

    contract = models.ForeignKey(FuturesContract, on_delete=models.CASCADE)
    source = models.ForeignKey(FinancialDataSource, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    open = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    high = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    low = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    close = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    volume = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    open_interest = models.DecimalField(
        max_digits=24, decimal_places=6, null=True, blank=True
    )
    settlement = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "source", "timestamp"],
                name="uniq_futures_snapshot",
            )
        ]

    def __str__(self) -> str:
        """Return the futures snapshot label."""
        return f"{self.contract_id}:{self.timestamp.isoformat()}"


class FundamentalFact(models.Model):
    """Normalized SEC or vendor fundamental fact."""

    instrument = models.ForeignKey(
        FinancialInstrument, null=True, blank=True, on_delete=models.SET_NULL
    )
    source = models.ForeignKey(FinancialDataSource, on_delete=models.CASCADE)
    cik = models.CharField(max_length=32, blank=True)
    taxonomy = models.CharField(max_length=64)
    tag = models.CharField(max_length=160)
    unit = models.CharField(max_length=32)
    fiscal_year = models.IntegerField(null=True, blank=True)
    fiscal_period = models.CharField(max_length=16, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    filed_at = models.DateTimeField(null=True, blank=True)
    value = models.DecimalField(max_digits=28, decimal_places=6)
    form_type = models.CharField(max_length=32, blank=True)
    accession_number = models.CharField(max_length=80, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["cik", "tag", "filed_at"])]

    def __str__(self) -> str:
        """Return the fundamental fact label."""
        return f"{self.cik}:{self.tag}:{self.fiscal_period}"


class MacroSeries(models.Model):
    """Macroeconomic series metadata."""

    provider = models.CharField(max_length=80)
    series_id = models.CharField(max_length=120)
    title = models.CharField(max_length=500)
    frequency = models.CharField(max_length=80, blank=True)
    units = models.CharField(max_length=120, blank=True)
    seasonal_adjustment = models.CharField(max_length=120, blank=True)
    source_notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "series_id"], name="uniq_macro_series"
            )
        ]

    def __str__(self) -> str:
        """Return the macro series label."""
        return f"{self.provider}:{self.series_id}"


class MacroObservation(models.Model):
    """Macroeconomic observation with realtime vintage."""

    series = models.ForeignKey(MacroSeries, on_delete=models.CASCADE)
    date = models.DateField()
    value = models.DecimalField(max_digits=28, decimal_places=6, null=True, blank=True)
    realtime_start = models.DateField(null=True, blank=True)
    realtime_end = models.DateField(null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["series", "date", "realtime_start"],
                name="uniq_macro_observation",
            )
        ]

    def __str__(self) -> str:
        """Return the macro observation label."""
        return f"{self.series_id}:{self.date.isoformat()}"


class GovernmentReport(models.Model):
    """Official public report captured with compliance metadata."""

    source = models.ForeignKey(FinancialDataSource, on_delete=models.CASCADE)
    report_type = models.CharField(max_length=80)
    jurisdiction = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1200)
    published_at = models.DateTimeField(null=True, blank=True)
    text = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the government report title."""
        return self.title


class CFTCCommitmentReport(models.Model):
    """Normalized CFTC Commitments of Traders row."""

    market_name = models.CharField(max_length=240)
    cftc_contract_market_code = models.CharField(max_length=32, blank=True)
    report_date = models.DateField()
    report_type = models.CharField(max_length=64)
    producer_merchant_long = models.FloatField(null=True, blank=True)
    producer_merchant_short = models.FloatField(null=True, blank=True)
    managed_money_long = models.FloatField(null=True, blank=True)
    managed_money_short = models.FloatField(null=True, blank=True)
    swap_dealer_long = models.FloatField(null=True, blank=True)
    swap_dealer_short = models.FloatField(null=True, blank=True)
    open_interest = models.FloatField(null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["market_name", "report_date", "report_type"],
                name="uniq_cftc_commitment_report",
            )
        ]

    def __str__(self) -> str:
        """Return the CFTC report label."""
        return f"{self.market_name}:{self.report_date.isoformat()}"


class FinancialRelationEdge(models.Model):
    """Typed graph edge between financial instruments."""

    source_instrument = models.ForeignKey(
        FinancialInstrument, on_delete=models.CASCADE, related_name="finance_out_edges"
    )
    target_instrument = models.ForeignKey(
        FinancialInstrument, on_delete=models.CASCADE, related_name="finance_in_edges"
    )
    relation_type = models.CharField(max_length=80)
    weight = models.FloatField(default=1.0)
    confidence = models.FloatField(default=1.0)
    evidence_type = models.CharField(max_length=80, blank=True)
    evidence_url = models.URLField(max_length=1200, blank=True)
    effective_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["relation_type", "effective_at"])]

    def __str__(self) -> str:
        """Return the financial relation label."""
        source_id = self.source_instrument_id
        target_id = self.target_instrument_id
        return f"{source_id}->{target_id}:{self.relation_type}"


class MultifractalFeatureSet(models.Model):
    """Stored multifractal and roughness feature vector."""

    instrument = models.ForeignKey(FinancialInstrument, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    window = models.PositiveIntegerField()
    method = models.CharField(max_length=80)
    q_grid_json = models.JSONField(default=list, blank=True)
    hurst_json = models.JSONField(default=dict, blank=True)
    tau_json = models.JSONField(default=dict, blank=True)
    alpha_json = models.JSONField(default=list, blank=True)
    f_alpha_json = models.JSONField(default=list, blank=True)
    spectrum_width = models.FloatField(default=0.0)
    roughness = models.FloatField(default=0.0)
    intermittency = models.FloatField(default=0.0)
    wavelet_energy_json = models.JSONField(default=dict, blank=True)
    imf_energy_json = models.JSONField(default=dict, blank=True)
    quality_flags_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the multifractal feature label."""
        return f"{self.instrument_id}:{self.method}:{self.timestamp.isoformat()}"


class StatisticalScore(models.Model):
    """Financial score used for model evaluation or feature building."""

    instrument = models.ForeignKey(FinancialInstrument, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    score_type = models.CharField(max_length=80)
    window = models.PositiveIntegerField()
    value = models.FloatField()
    components_json = models.JSONField(default=dict, blank=True)
    quality_flags_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the statistical score label."""
        return f"{self.instrument_id}:{self.score_type}:{self.timestamp.isoformat()}"


class PredictionDatasetManifest(models.Model):
    """Manifest for a leakage-controlled finance prediction dataset."""

    name = models.CharField(max_length=180, unique=True)
    universe_json = models.JSONField(default=list, blank=True)
    horizon = models.CharField(max_length=80)
    feature_flags_json = models.JSONField(default=dict, blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    row_count = models.PositiveIntegerField(default=0)
    target_definition = models.TextField()
    parquet_path = models.CharField(max_length=1200, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return the dataset manifest name."""
        return self.name

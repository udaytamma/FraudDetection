"""
Prometheus Metrics

Defines all metrics exposed by the fraud detection service.
Metrics are critical for:
- SLA monitoring (latency targets)
- Business metrics (approval rate, fraud rate)
- Operational health (error rates, component health)
"""

import logging

from prometheus_client import Counter, Histogram, Gauge, start_http_server

from ..config import settings

logger = logging.getLogger("fraud_detection.metrics")


class FraudMetrics:
    """
    Container for all Prometheus metrics.

    Organized by category:
    - Request metrics
    - Latency metrics
    - Decision metrics
    - Scoring metrics
    - System metrics
    """

    def __init__(self):
        """Initialize all metrics."""

        # =====================================================================
        # Request Metrics
        # =====================================================================
        self.requests_total = Counter(
            "fraud_requests_total",
            "Total number of fraud check requests",
            labelnames=["endpoint"],
        )

        self.errors_total = Counter(
            "fraud_errors_total",
            "Total number of errors",
            labelnames=["error_type"],
        )

        # =====================================================================
        # Latency Metrics
        # =====================================================================
        # End-to-end latency (target: <200ms)
        self.e2e_latency = Histogram(
            "fraud_e2e_latency_ms",
            "End-to-end processing latency in milliseconds",
            buckets=[10, 25, 50, 75, 100, 150, 200, 250, 300, 500, 1000],
        )

        # Feature computation latency (target: <50ms)
        self.feature_latency = Histogram(
            "fraud_feature_latency_ms",
            "Feature computation latency in milliseconds",
            buckets=[5, 10, 20, 30, 40, 50, 75, 100],
        )

        # Scoring latency (target: <25ms)
        self.scoring_latency = Histogram(
            "fraud_scoring_latency_ms",
            "Risk scoring latency in milliseconds",
            buckets=[5, 10, 15, 20, 25, 35, 50],
        )

        # Policy evaluation latency
        self.policy_latency = Histogram(
            "fraud_policy_latency_ms",
            "Policy evaluation latency in milliseconds",
            buckets=[1, 2, 5, 10, 15, 20],
        )

        # Slow requests counter (exceeds SLA)
        self.slow_requests = Counter(
            "fraud_slow_requests_total",
            "Number of requests exceeding latency SLA",
        )

        # =====================================================================
        # Decision Metrics
        # =====================================================================
        self.decisions_total = Counter(
            "fraud_decisions_total",
            "Total number of decisions by type",
            labelnames=["decision"],
        )

        # Approval rate gauge (updated periodically)
        self.approval_rate = Gauge(
            "fraud_approval_rate",
            "Current approval rate (rolling 1 hour)",
        )

        # Block rate gauge
        self.block_rate = Gauge(
            "fraud_block_rate",
            "Current block rate (rolling 1 hour)",
        )

        # =====================================================================
        # Scoring Metrics
        # =====================================================================
        self.risk_score_distribution = Histogram(
            "fraud_risk_score",
            "Distribution of risk scores",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        self.criminal_score_distribution = Histogram(
            "fraud_criminal_score",
            "Distribution of criminal fraud scores",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        self.friendly_score_distribution = Histogram(
            "fraud_friendly_score",
            "Distribution of friendly fraud scores",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        # =====================================================================
        # Cache Metrics
        # =====================================================================
        self.cache_hits = Counter(
            "fraud_cache_hits_total",
            "Number of idempotency cache hits",
        )

        self.cache_misses = Counter(
            "fraud_cache_misses_total",
            "Number of idempotency cache misses",
        )

        # =====================================================================
        # Detector Metrics
        # =====================================================================
        self.detector_triggers = Counter(
            "fraud_detector_triggers_total",
            "Number of times each detector triggered",
            labelnames=["detector"],
        )

        # =====================================================================
        # System Metrics
        # =====================================================================
        self.redis_latency = Histogram(
            "fraud_redis_latency_ms",
            "Redis operation latency in milliseconds",
            buckets=[1, 2, 5, 10, 20, 50],
        )

        self.postgres_latency = Histogram(
            "fraud_postgres_latency_ms",
            "PostgreSQL operation latency in milliseconds",
            buckets=[5, 10, 25, 50, 100, 250],
        )

        # Component health
        self.component_health = Gauge(
            "fraud_component_health",
            "Component health status (1=healthy, 0=unhealthy)",
            labelnames=["component"],
        )

        # Policy version
        self.policy_version_info = Gauge(
            "fraud_policy_version",
            "Current policy version (hash as value)",
        )


# Global metrics instance
metrics = FraudMetrics()


def setup_metrics() -> None:
    """
    Setup Prometheus metrics server.

    Starts HTTP server on configured port to expose metrics.
    """
    if settings.metrics_enabled:
        try:
            start_http_server(settings.metrics_port)
            logger.info("Metrics server started on port %d", settings.metrics_port)
        except Exception as e:
            logger.warning("Failed to start metrics server: %s", e)


def update_rates(allow_count: int, block_count: int, total_count: int) -> None:
    """
    Update rate gauges.

    Called periodically to update approval/block rates.

    Args:
        allow_count: Number of ALLOW decisions
        block_count: Number of BLOCK decisions
        total_count: Total decisions
    """
    if total_count > 0:
        metrics.approval_rate.set(allow_count / total_count)
        metrics.block_rate.set(block_count / total_count)

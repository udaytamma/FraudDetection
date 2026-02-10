"""
Model Monitoring

Tracks per-variant decision rates, fallback rates, and
fraud/approval rates for ML scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..metrics import metrics
from ..schemas import RiskScores


@dataclass
class VariantStats:
    total: int = 0
    approvals: int = 0
    blocks: int = 0
    frauds: int = 0
    fallbacks: int = 0

    def approval_rate(self) -> float:
        return self.approvals / self.total if self.total else 0.0

    def fraud_rate(self) -> float:
        return self.frauds / self.total if self.total else 0.0

    def fallback_rate(self) -> float:
        return self.fallbacks / self.total if self.total else 0.0


class ModelMonitor:
    """In-memory model monitoring with optional Prometheus export."""

    def __init__(self, metrics_enabled: bool = True) -> None:
        self.metrics_enabled = metrics_enabled
        self._stats: dict[str, VariantStats] = {}

    def record_decision(self, decision: str, scores: RiskScores) -> None:
        variant = scores.model_variant or "rules_only"
        decision_value = decision.value if hasattr(decision, "value") else str(decision)
        stats = self._stats.setdefault(variant, VariantStats())
        stats.total += 1
        if decision_value == "ALLOW":
            stats.approvals += 1
        else:
            stats.blocks += 1

        ml_available = scores.ml_score is not None
        if not ml_available and variant not in {"holdout", "rules_only"}:
            stats.fallbacks += 1

        if self.metrics_enabled:
            metrics.model_decisions_total.labels(variant=variant, decision=decision_value).inc()
            if not ml_available and variant not in {"holdout", "rules_only"}:
                metrics.model_fallback_total.labels(variant=variant).inc()
            metrics.model_approval_rate.labels(variant=variant).set(stats.approval_rate())
            metrics.model_fraud_rate.labels(variant=variant).set(stats.fraud_rate())
            metrics.model_fallback_rate.labels(variant=variant).set(stats.fallback_rate())

    def record_outcome(self, variant: Optional[str], is_fraud: bool) -> None:
        variant = variant or "rules_only"
        stats = self._stats.setdefault(variant, VariantStats())
        if is_fraud:
            stats.frauds += 1
        if self.metrics_enabled:
            metrics.model_fraud_rate.labels(variant=variant).set(stats.fraud_rate())

    def snapshot(self) -> dict:
        return {
            variant: {
                "total": stats.total,
                "approvals": stats.approvals,
                "blocks": stats.blocks,
                "frauds": stats.frauds,
                "fallbacks": stats.fallbacks,
                "approval_rate": round(stats.approval_rate(), 4),
                "fraud_rate": round(stats.fraud_rate(), 4),
                "fallback_rate": round(stats.fallback_rate(), 4),
            }
            for variant, stats in self._stats.items()
        }

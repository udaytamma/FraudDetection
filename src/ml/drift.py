"""
Feature Drift Detection

Computes Population Stability Index (PSI) to detect
feature distribution shifts between a baseline window
and the current window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import create_engine, text

from ..config import settings
from .features import FEATURE_COLUMNS, extract_from_snapshot, vector_from_feature_dict


@dataclass
class DriftScore:
    feature: str
    psi: float
    significant: bool


@dataclass
class DriftReport:
    baseline_start: datetime
    baseline_end: datetime
    current_start: datetime
    current_end: datetime
    threshold: float
    scores: list[DriftScore]

    def to_dict(self) -> dict:
        return {
            "baseline_start": self.baseline_start.isoformat(),
            "baseline_end": self.baseline_end.isoformat(),
            "current_start": self.current_start.isoformat(),
            "current_end": self.current_end.isoformat(),
            "threshold": self.threshold,
            "scores": [
                {
                    "feature": score.feature,
                    "psi": score.psi,
                    "significant": score.significant,
                }
                for score in self.scores
            ],
            "significant_features": [score.feature for score in self.scores if score.significant],
            "max_psi": max((score.psi for score in self.scores), default=0.0),
        }


def _load_feature_matrix(
    start: datetime,
    end: datetime,
    postgres_url: Optional[str] = None,
) -> np.ndarray:
    engine = create_engine(postgres_url or settings.postgres_sync_url)
    query = text(
        """
        SELECT
            e.features_snapshot
        FROM transaction_evidence e
        WHERE e.captured_at >= :start
          AND e.captured_at < :end
        ORDER BY e.captured_at ASC
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            query,
            {
                "start": start,
                "end": end,
            },
        ).mappings().all()

    vectors: list[list[float]] = []
    for row in rows:
        snapshot = row.get("features_snapshot")
        if snapshot is None:
            continue
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                continue
        if not isinstance(snapshot, dict):
            continue
        feature_dict = extract_from_snapshot(snapshot)
        vectors.append(vector_from_feature_dict(feature_dict))

    if not vectors:
        return np.array([])

    return np.array(vectors, dtype=float)


def compute_psi(
    baseline: np.ndarray,
    current: np.ndarray,
    buckets: int = 10,
    epsilon: float = 1e-6,
) -> float:
    if baseline.size == 0 or current.size == 0:
        return 0.0

    baseline = np.asarray(baseline, dtype=float)
    current = np.asarray(current, dtype=float)

    quantiles = np.linspace(0, 1, buckets + 1)
    bins = np.quantile(baseline, quantiles)
    bins[0] = -np.inf
    bins[-1] = np.inf
    bins = np.unique(bins)

    if len(bins) < 3:
        return 0.0

    base_counts, _ = np.histogram(baseline, bins=bins)
    cur_counts, _ = np.histogram(current, bins=bins)

    base_pct = base_counts / max(base_counts.sum(), 1)
    cur_pct = cur_counts / max(cur_counts.sum(), 1)

    psi = np.sum((cur_pct - base_pct) * np.log((cur_pct + epsilon) / (base_pct + epsilon)))
    return float(round(psi, 4))


def compute_drift_report(
    baseline_start: datetime,
    baseline_end: datetime,
    current_start: datetime,
    current_end: datetime,
    threshold: float = 0.2,
    postgres_url: Optional[str] = None,
) -> DriftReport:
    baseline_matrix = _load_feature_matrix(baseline_start, baseline_end, postgres_url)
    current_matrix = _load_feature_matrix(current_start, current_end, postgres_url)

    scores: list[DriftScore] = []
    if baseline_matrix.size == 0 or current_matrix.size == 0:
        for feature in FEATURE_COLUMNS:
            scores.append(DriftScore(feature=feature, psi=0.0, significant=False))
        return DriftReport(
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            current_start=current_start,
            current_end=current_end,
            threshold=threshold,
            scores=scores,
        )

    for idx, feature in enumerate(FEATURE_COLUMNS):
        base_col = baseline_matrix[:, idx]
        cur_col = current_matrix[:, idx]
        psi = compute_psi(base_col, cur_col)
        scores.append(DriftScore(feature=feature, psi=psi, significant=psi > threshold))

    return DriftReport(
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        current_start=current_start,
        current_end=current_end,
        threshold=threshold,
        scores=scores,
    )

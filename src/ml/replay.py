"""
Offline Replay Framework

Re-scores historical evidence using a specified ML model and
compares results to original decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import numpy as np
from sqlalchemy import create_engine, text

from ..config import settings
from .features import FEATURE_COLUMNS, extract_from_snapshot, vector_from_feature_dict

CRIMINAL_REASON_CODES = {
    "10.1",
    "10.2",
    "10.3",
    "10.4",
    "10.5",
}


@dataclass
class ReplayMetrics:
    total: int
    fraud_count: int
    approval_rate: float
    fraud_caught_rate: float
    false_positive_rate: float


@dataclass
class ReplayResults:
    original: ReplayMetrics
    replayed: ReplayMetrics
    approval_rate_delta: float
    fraud_caught_delta: float
    false_positive_delta: float

    def to_dict(self) -> dict:
        return {
            "original": self.original.__dict__,
            "replayed": self.replayed.__dict__,
            "approval_rate_delta": self.approval_rate_delta,
            "fraud_caught_delta": self.fraud_caught_delta,
            "false_positive_delta": self.false_positive_delta,
        }


def _load_rows(start: datetime, end: datetime, postgres_url: Optional[str]) -> list[dict]:
    engine = create_engine(postgres_url or settings.postgres_sync_url)
    query = text(
        """
        SELECT
            e.transaction_id,
            e.captured_at,
            e.features_snapshot,
            e.decision,
            MAX(
                CASE
                    WHEN c.fraud_type = 'CRIMINAL' THEN 1
                    WHEN c.reason_code IN :reason_codes THEN 1
                    ELSE 0
                END
            ) AS label
        FROM transaction_evidence e
        LEFT JOIN chargebacks c ON c.transaction_id = e.transaction_id
        WHERE e.captured_at >= :start
          AND e.captured_at < :end
        GROUP BY e.transaction_id, e.captured_at, e.features_snapshot, e.decision
        ORDER BY e.captured_at ASC
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            query,
            {
                "start": start,
                "end": end,
                "reason_codes": tuple(CRIMINAL_REASON_CODES),
            },
        ).mappings().all()
    return [dict(row) for row in rows]


def _load_model(model_path: str, model_type: str):
    if model_type == "xgb_classifier":
        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        return model
    if model_type == "lgbm_classifier":
        import lightgbm as lgb
        return lgb.Booster(model_file=model_path)
    raise ValueError(f"Unsupported model_type: {model_type}")


def _predict(model: object, model_type: str, X: np.ndarray) -> np.ndarray:
    if model_type == "xgb_classifier":
        probas = model.predict_proba(X)[:, 1]  # type: ignore[attr-defined]
        return np.asarray(probas)
    if model_type == "lgbm_classifier":
        probas = model.predict(X)  # type: ignore[attr-defined]
        return np.asarray(probas)
    raise ValueError(f"Unsupported model_type: {model_type}")


def _build_dataset(rows: Iterable[dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    features_list: list[list[float]] = []
    labels: list[int] = []
    decisions: list[str] = []

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
        vector = vector_from_feature_dict(feature_dict)
        features_list.append(vector)
        labels.append(int(row.get("label") or 0))
        decisions.append(row.get("decision") or "ALLOW")

    if not features_list:
        return np.array([]), np.array([]), []

    return np.array(features_list, dtype=float), np.array(labels, dtype=int), decisions


def _compute_metrics(decisions: list[str], labels: np.ndarray) -> ReplayMetrics:
    total = len(decisions)
    if total == 0:
        return ReplayMetrics(total=0, fraud_count=0, approval_rate=0.0, fraud_caught_rate=0.0, false_positive_rate=0.0)

    fraud_count = int(labels.sum())
    approvals = sum(1 for d in decisions if d == "ALLOW")
    denies = [d for d in decisions if d != "ALLOW"]

    fraud_caught = sum(1 for d, label in zip(decisions, labels) if label == 1 and d != "ALLOW")
    false_positive = sum(1 for d, label in zip(decisions, labels) if label == 0 and d != "ALLOW")

    approval_rate = approvals / total
    fraud_caught_rate = (fraud_caught / fraud_count) if fraud_count else 0.0
    false_positive_rate = (false_positive / (total - fraud_count)) if total != fraud_count else 0.0

    return ReplayMetrics(
        total=total,
        fraud_count=fraud_count,
        approval_rate=round(approval_rate, 4),
        fraud_caught_rate=round(fraud_caught_rate, 4),
        false_positive_rate=round(false_positive_rate, 4),
    )


def replay(
    start: datetime,
    end: datetime,
    model_path: str,
    model_type: str,
    threshold: float,
    postgres_url: Optional[str] = None,
) -> ReplayResults:
    rows = _load_rows(start, end, postgres_url)
    X, y, decisions = _build_dataset(rows)
    if X.size == 0:
        raise ValueError("No usable feature snapshots found for replay window")

    model = _load_model(model_path, model_type)
    scores = _predict(model, model_type, X)

    replayed_decisions = ["BLOCK" if score >= threshold else "ALLOW" for score in scores]

    original_metrics = _compute_metrics(decisions, y)
    replayed_metrics = _compute_metrics(replayed_decisions, y)

    return ReplayResults(
        original=original_metrics,
        replayed=replayed_metrics,
        approval_rate_delta=round(replayed_metrics.approval_rate - original_metrics.approval_rate, 4),
        fraud_caught_delta=round(replayed_metrics.fraud_caught_rate - original_metrics.fraud_caught_rate, 4),
        false_positive_delta=round(replayed_metrics.false_positive_rate - original_metrics.false_positive_rate, 4),
    )


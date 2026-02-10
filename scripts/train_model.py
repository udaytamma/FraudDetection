"""
Phase 2 ML Training Pipeline

Trains champion/challenger models from evidence + chargeback labels.
Defaults align with the Phase 2 roadmap:
- 90-day training window
- 120-day label maturity cutoff
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Iterable

import numpy as np
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.ml.features import FEATURE_COLUMNS, extract_from_snapshot, vector_from_feature_dict
from src.ml.registry import ModelEntry, ModelRegistry

logger = logging.getLogger("fraud_detection.train")

CRIMINAL_REASON_CODES = {
    "10.1",
    "10.2",
    "10.3",
    "10.4",
    "10.5",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Phase 2 fraud ML models")
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--maturity-days", type=int, default=120)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--registry-path", type=str, default=str(ROOT / "models" / "registry.json"))
    parser.add_argument("--output-dir", type=str, default=str(ROOT / "models"))
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--min-auc", type=float, default=0.85)
    parser.add_argument("--validation-days", type=int, default=7)
    return parser.parse_args()


def compute_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if args.end_date:
        end = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end = now - timedelta(days=args.maturity_days)
    start = end - timedelta(days=args.window_days)
    return start, end


def load_training_rows(start: datetime, end: datetime) -> list[dict]:
    engine = create_engine(settings.postgres_sync_url)
    query = text(
        """
        SELECT
            e.transaction_id,
            e.captured_at,
            e.features_snapshot,
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
        GROUP BY e.transaction_id, e.captured_at, e.features_snapshot
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


def build_dataset(rows: Iterable[dict]) -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    features_list: list[list[float]] = []
    labels: list[int] = []
    timestamps: list[datetime] = []

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
        timestamps.append(row.get("captured_at"))

    if not features_list:
        return np.array([]), np.array([]), []

    return np.array(features_list, dtype=float), np.array(labels, dtype=int), timestamps


def time_split(
    X: np.ndarray,
    y: np.ndarray,
    timestamps: list[datetime],
    validation_days: int = 7,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not timestamps:
        return X, y, np.array([]), np.array([])

    cutoff = max(timestamps) - timedelta(days=validation_days)
    train_idx = [i for i, ts in enumerate(timestamps) if ts <= cutoff]
    val_idx = [i for i, ts in enumerate(timestamps) if ts > cutoff]

    if not val_idx:
        return X, y, np.array([]), np.array([])

    return X[train_idx], y[train_idx], X[val_idx], y[val_idx]


def train_xgboost(X_train: np.ndarray, y_train: np.ndarray):
    import xgboost as xgb

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="auc",
        tree_method="hist",
    )
    model.fit(X_train, y_train)
    return model


def train_lightgbm(X_train: np.ndarray, y_train: np.ndarray):
    import lightgbm as lgb

    model = lgb.LGBMClassifier(
        n_estimators=200,
        max_depth=-1,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
    )
    model.fit(X_train, y_train)
    return model


def compute_auc(model, X_val: np.ndarray, y_val: np.ndarray) -> float | None:
    if X_val.size == 0:
        return None
    from sklearn.metrics import roc_auc_score

    if hasattr(model, "predict_proba"):
        probas = model.predict_proba(X_val)[:, 1]
    else:
        probas = model.predict(X_val)
    return float(roc_auc_score(y_val, probas))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    args = parse_args()
    start, end = compute_window(args)

    logger.info("Training window: %s to %s", start.isoformat(), end.isoformat())
    rows = load_training_rows(start, end)
    if len(rows) < args.min_rows:
        logger.warning("Insufficient training rows (%d); need >= %d", len(rows), args.min_rows)
        return

    X, y, timestamps = build_dataset(rows)
    if X.size == 0:
        logger.warning("No usable feature snapshots found")
        return

    X_train, y_train, X_val, y_val = time_split(X, y, timestamps, validation_days=args.validation_days)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(UTC).isoformat()
    registry = ModelRegistry(args.registry_path)

    try:
        xgb_model = train_xgboost(X_train, y_train)
        xgb_auc = compute_auc(xgb_model, X_val, y_val)
        xgb_version = f"xgb-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        xgb_path = output_dir / f"{xgb_version}.json"
        xgb_model.save_model(str(xgb_path))

        registry.set(
            "champion",
            ModelEntry(
                name="xgboost_criminal",
                version=xgb_version,
                path=str(xgb_path),
                framework="xgboost",
                model_type="xgb_classifier",
                trained_at=trained_at,
                auc=xgb_auc,
                feature_columns=FEATURE_COLUMNS,
                window_start=start.isoformat(),
                window_end=end.isoformat(),
            ),
        )
        if xgb_auc is not None and xgb_auc < args.min_auc:
            logger.warning("Champion AUC %.4f below min %.4f (registered anyway)", xgb_auc, args.min_auc)
        logger.info("Saved champion model: %s (AUC=%s)", xgb_version, xgb_auc)
    except Exception as exc:
        logger.warning("XGBoost training failed: %s", exc)

    try:
        lgb_model = train_lightgbm(X_train, y_train)
        lgb_auc = compute_auc(lgb_model, X_val, y_val)
        lgb_version = f"lgbm-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        lgb_path = output_dir / f"{lgb_version}.txt"
        lgb_model.booster_.save_model(str(lgb_path))

        if lgb_auc is None:
            logger.warning("No validation AUC for challenger; skipping registry update")
        elif lgb_auc < args.min_auc:
            logger.warning("Challenger AUC %.4f below min %.4f; skipping registry update", lgb_auc, args.min_auc)
        else:
            registry.set(
                "challenger",
                ModelEntry(
                    name="lightgbm_criminal",
                    version=lgb_version,
                    path=str(lgb_path),
                    framework="lightgbm",
                    model_type="lgbm_classifier",
                    trained_at=trained_at,
                    auc=lgb_auc,
                    feature_columns=FEATURE_COLUMNS,
                    window_start=start.isoformat(),
                    window_end=end.isoformat(),
                ),
            )
            logger.info("Saved challenger model: %s (AUC=%s)", lgb_version, lgb_auc)
    except Exception as exc:
        logger.warning("LightGBM training failed: %s", exc)


if __name__ == "__main__":
    main()

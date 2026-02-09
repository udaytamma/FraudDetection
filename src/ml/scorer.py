"""
ML Scoring

Loads models from the registry and produces ML scores
with champion/challenger routing.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..schemas import FeatureSet
from .features import FEATURE_COLUMNS, extract_feature_dict, vector_from_feature_dict
from .registry import ModelRegistry

logger = logging.getLogger("fraud_detection.ml")


@dataclass
class MLScoreResult:
    score: Optional[float]
    model_version: Optional[str]
    model_variant: Optional[str]
    latency_ms: float


class MLScorer:
    """Scores transactions using champion/challenger ML models."""

    def __init__(
        self,
        registry_path: str,
        challenger_percent: int = 15,
        holdout_percent: int = 5,
    ) -> None:
        self.registry = ModelRegistry(registry_path)
        self.challenger_percent = max(0, min(100, challenger_percent))
        self.holdout_percent = max(0, min(100, holdout_percent))
        self._models: dict[str, object] = {}

    def _route_variant(self, routing_key: str) -> str:
        """Deterministically route traffic based on routing_key."""
        if not routing_key:
            return "champion"
        digest = hashlib.sha256(routing_key.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        if bucket < self.holdout_percent:
            return "holdout"
        if bucket < self.holdout_percent + self.challenger_percent:
            return "challenger"
        return "champion"

    def _load_model(self, entry_name: str, entry_path: str, model_type: str):
        cache_key = f"{entry_name}:{entry_path}"
        if cache_key in self._models:
            return self._models[cache_key]

        if not entry_path:
            return None

        model_path = Path(entry_path)
        if not model_path.is_absolute():
            model_path = Path.cwd() / model_path

        if not model_path.exists():
            logger.warning("Model file not found: %s", model_path)
            return None

        if model_type == "xgb_classifier":
            try:
                import xgboost as xgb
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("xgboost not available: %s", exc)
                return None
            model = xgb.XGBClassifier()
            model.load_model(str(model_path))
            self._models[cache_key] = model
            return model

        if model_type == "lgbm_classifier":
            try:
                import lightgbm as lgb
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("lightgbm not available: %s", exc)
                return None
            model = lgb.Booster(model_file=str(model_path))
            self._models[cache_key] = model
            return model

        logger.warning("Unsupported model_type: %s", model_type)
        return None

    def _predict(self, model: object, model_type: str, vector: list[float]) -> Optional[float]:
        if model_type == "xgb_classifier":
            import numpy as np
            vector_np = np.array(vector, dtype=float).reshape(1, -1)
            proba = model.predict_proba(vector_np)
            return float(proba[0][1])

        if model_type == "lgbm_classifier":
            import numpy as np
            vector_np = np.array(vector, dtype=float).reshape(1, -1)
            proba = model.predict(vector_np)
            if isinstance(proba, (list, tuple)):
                return float(proba[0])
            return float(proba)

        return None

    def score(self, features: FeatureSet, routing_key: str) -> MLScoreResult:
        """Score a FeatureSet using routed ML model."""
        started = time.perf_counter()
        variant = self._route_variant(routing_key)

        if variant == "holdout":
            return MLScoreResult(
                score=None,
                model_version=None,
                model_variant="holdout",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        entry = self.registry.get(variant)
        if not entry:
            return MLScoreResult(
                score=None,
                model_version=None,
                model_variant=variant,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        model = self._load_model(entry.name, entry.path, entry.model_type)
        if not model:
            return MLScoreResult(
                score=None,
                model_version=entry.version,
                model_variant=variant,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        feature_values = extract_feature_dict(features)
        vector = vector_from_feature_dict(feature_values)
        score = self._predict(model, entry.model_type, vector)
        elapsed = (time.perf_counter() - started) * 1000

        if score is None:
            return MLScoreResult(
                score=None,
                model_version=entry.version,
                model_variant=variant,
                latency_ms=elapsed,
            )

        return MLScoreResult(
            score=max(0.0, min(1.0, score)),
            model_version=entry.version,
            model_variant=variant,
            latency_ms=elapsed,
        )


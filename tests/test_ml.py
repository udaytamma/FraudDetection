import sys
import types
from types import SimpleNamespace

import pytest

from src.config import settings
from src.ml.features import (
    FEATURE_COLUMNS,
    extract_feature_dict,
    extract_from_snapshot,
    vector_from_feature_dict,
)
from src.ml.registry import ModelEntry, ModelRegistry
from src.ml.scorer import MLScorer, MLScoreResult
from src.schemas import FeatureSet, PaymentEvent
from src.scoring.risk_scorer import RiskScorer


def _sample_event() -> PaymentEvent:
    return PaymentEvent(
        transaction_id="txn_123",
        idempotency_key="idem_123",
        amount_cents=1000,
        card_token="card_123",
        service_id="svc_123",
    )


def test_feature_vector_length_and_null_handling():
    features = FeatureSet()
    feature_dict = extract_feature_dict(features)
    vector = vector_from_feature_dict(feature_dict)

    assert len(vector) == len(FEATURE_COLUMNS)
    assert all(isinstance(value, float) for value in vector)

    snapshot = {
        "velocity": {
            "card_attempts_1h": None,
            "card_declines_1h": None,
        },
        "entity": {
            "card_age_hours": None,
        },
        "transaction": {
            "amount_usd": None,
        },
    }
    extracted = extract_from_snapshot(snapshot)
    assert extracted["card_attempts_1h"] == 0.0
    assert extracted["card_decline_rate_1h"] == 0.0
    assert extracted["card_age_hours"] == 0.0
    assert extracted["amount_usd"] == 0.0


def test_snapshot_extraction_consistency():
    features = FeatureSet(
        amount_cents=1500,
        amount_usd=15.0,
        amount_zscore=1.2,
        hour_of_day=13,
        is_weekend=True,
        is_new_card_for_user=True,
        is_new_device_for_user=False,
    )
    features.velocity.card_attempts_1h = 5
    features.velocity.card_attempts_10m = 1
    features.velocity.card_declines_1h = 1
    features.velocity.device_distinct_cards_1h = 2
    features.velocity.device_distinct_cards_24h = 3
    features.velocity.ip_distinct_cards_1h = 2
    features.velocity.user_amount_24h_cents = 2500
    features.velocity.card_distinct_devices_30d = 4
    features.velocity.card_distinct_users_30d = 2

    features.entity.card_age_hours = 24
    features.entity.device_age_hours = 12
    features.entity.user_account_age_days = 90
    features.entity.user_chargeback_count = 1
    features.entity.user_chargeback_rate_90d = 0.05
    features.entity.user_refund_count_90d = 2
    features.entity.device_is_emulator = False
    features.entity.device_is_rooted = True
    features.entity.ip_is_datacenter = False
    features.entity.ip_is_vpn = True
    features.entity.ip_is_tor = False
    features.entity.ip_risk_score = 0.4

    snapshot = {
        "velocity": {
            "card_attempts_10m": 1,
            "card_attempts_1h": 5,
            "card_attempts_24h": 0,
            "device_distinct_cards_1h": 2,
            "device_distinct_cards_24h": 3,
            "ip_distinct_cards_1h": 2,
            "user_amount_24h_cents": 2500,
            "card_declines_1h": 1,
            "card_distinct_devices_30d": 4,
            "card_distinct_users_30d": 2,
        },
        "entity": {
            "card_age_hours": 24,
            "device_age_hours": 12,
            "user_account_age_days": 90,
            "user_chargeback_count": 1,
            "user_chargeback_rate_90d": 0.05,
            "user_refund_count_90d": 2,
            "device_is_emulator": False,
            "device_is_rooted": True,
            "ip_is_datacenter": False,
            "ip_is_vpn": True,
            "ip_is_tor": False,
            "ip_risk_score": 0.4,
        },
        "transaction": {
            "amount_usd": 15.0,
            "amount_zscore": 1.2,
            "is_new_card_for_user": True,
            "is_new_device_for_user": False,
            "hour_of_day": 13,
            "is_weekend": True,
        },
    }

    vector_features = vector_from_feature_dict(extract_feature_dict(features))
    vector_snapshot = vector_from_feature_dict(extract_from_snapshot(snapshot))

    assert vector_features == vector_snapshot


def test_registry_round_trip(tmp_path):
    path = tmp_path / "registry.json"
    registry = ModelRegistry(str(path))
    entry = ModelEntry(
        name="xgb",
        version="v1",
        path="models/xgb.json",
        framework="xgboost",
        model_type="xgb_classifier",
        trained_at="2026-01-01T00:00:00Z",
        auc=0.91,
        feature_columns=["a", "b"],
        window_start="2025-01-01",
        window_end="2025-04-01",
    )
    registry.set("champion", entry)

    registry_loaded = ModelRegistry(str(path))
    loaded = registry_loaded.get("champion")
    assert loaded is not None
    assert loaded.name == entry.name
    assert loaded.version == entry.version
    assert loaded.path == entry.path
    assert loaded.auc == entry.auc


def test_registry_ensure_default(tmp_path):
    path = tmp_path / "registry.json"
    registry = ModelRegistry(str(path))
    entry = ModelEntry(
        name="xgb",
        version="v1",
        path="models/xgb.json",
        framework="xgboost",
        model_type="xgb_classifier",
        trained_at="2026-01-01T00:00:00Z",
    )
    registry.ensure_default(entry)
    assert registry.get("champion") is not None


def test_routing_deterministic_and_distribution(tmp_path):
    scorer = MLScorer(str(tmp_path / "registry.json"), challenger_percent=15, holdout_percent=5)
    key = "stable-key"
    assert scorer._route_variant(key) == scorer._route_variant(key)

    counts = {"champion": 0, "challenger": 0, "holdout": 0}
    for i in range(10000):
        variant = scorer._route_variant(f"user-{i}")
        counts[variant] += 1

    holdout_rate = counts["holdout"] / 10000
    challenger_rate = counts["challenger"] / 10000

    assert 0.03 <= holdout_rate <= 0.07
    assert 0.12 <= challenger_rate <= 0.18


def test_holdout_returns_none_score(tmp_path):
    scorer = MLScorer(str(tmp_path / "registry.json"), challenger_percent=0, holdout_percent=100)
    result = scorer.score(FeatureSet(), "any-key")
    assert result.score is None
    assert result.model_variant == "holdout"


def test_model_loading_missing_file(tmp_path):
    scorer = MLScorer(str(tmp_path / "registry.json"))
    model = scorer._load_model("champion", str(tmp_path / "missing.json"), "xgb_classifier")
    assert model is None


def test_model_loading_cache(tmp_path, monkeypatch):
    load_calls = {"count": 0}

    class FakeXGBClassifier:
        def load_model(self, path: str) -> None:
            load_calls["count"] += 1

    fake_module = types.SimpleNamespace(XGBClassifier=FakeXGBClassifier)
    monkeypatch.setitem(sys.modules, "xgboost", fake_module)

    scorer = MLScorer(str(tmp_path / "registry.json"))
    model_path = tmp_path / "model.json"
    model_path.write_text("fake")

    first = scorer._load_model("champion", str(model_path), "xgb_classifier")
    second = scorer._load_model("champion", str(model_path), "xgb_classifier")

    assert first is second
    assert load_calls["count"] == 1


@pytest.mark.asyncio
async def test_ensemble_scoring_blend_and_overrides(monkeypatch):
    scorer = RiskScorer()

    async def fake_run_detection(event, features):
        results = {
            "CardTestingDetector": SimpleNamespace(score=0.2),
            "VelocityAttackDetector": SimpleNamespace(score=0.4),
            "GeoAnomalyDetector": SimpleNamespace(score=0.1),
            "BotDetector": SimpleNamespace(score=0.5),
            "FriendlyFraudDetector": SimpleNamespace(score=0.1),
        }
        return results, []

    scorer.detection_engine.run_detection = fake_run_detection

    class StubMLScorer:
        def score(self, features, routing_key):
            return MLScoreResult(score=0.8, model_version="v1", model_variant="champion", latency_ms=1.0)

    scorer.ml_scorer = StubMLScorer()

    event = _sample_event()
    features = FeatureSet()

    scores, _ = await scorer.compute_scores(event, features)

    rule_criminal_score = max(0.2 * 1.0, 0.4 * 0.9, 0.1 * 0.7, 0.5 * 1.0)
    expected_combined = (0.8 * settings.ml_weight) + (rule_criminal_score * (1 - settings.ml_weight))

    assert abs(scores.criminal_score - expected_combined) < 1e-6

    features.entity.device_is_emulator = True
    scores_emulator, _ = await scorer.compute_scores(event, features)
    assert scores_emulator.criminal_score >= 0.95


@pytest.mark.asyncio
async def test_ensemble_scoring_fallback_to_rules(monkeypatch):
    scorer = RiskScorer()

    async def fake_run_detection(event, features):
        results = {
            "CardTestingDetector": SimpleNamespace(score=0.2),
            "VelocityAttackDetector": SimpleNamespace(score=0.4),
            "GeoAnomalyDetector": SimpleNamespace(score=0.1),
            "BotDetector": SimpleNamespace(score=0.5),
            "FriendlyFraudDetector": SimpleNamespace(score=0.1),
        }
        return results, []

    scorer.detection_engine.run_detection = fake_run_detection

    class StubMLScorer:
        def score(self, features, routing_key):
            return MLScoreResult(score=None, model_version=None, model_variant="champion", latency_ms=1.0)

    scorer.ml_scorer = StubMLScorer()

    event = _sample_event()
    features = FeatureSet()

    scores, _ = await scorer.compute_scores(event, features)

    rule_criminal_score = max(0.2 * 1.0, 0.4 * 0.9, 0.1 * 0.7, 0.5 * 1.0)
    assert abs(scores.criminal_score - rule_criminal_score) < 1e-6

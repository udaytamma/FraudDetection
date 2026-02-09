"""
Sanity test suite covering unit, integration, and system tiers.
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from pathlib import Path

import pytest
import httpx
from pydantic import ValidationError

from src.schemas import (
    PaymentEvent,
    DeviceInfo,
    GeoInfo,
    VerificationInfo,
    Decision,
    RiskScores,
    VelocityFeatures,
    FeatureSet,
    FraudDecisionResponse,
)
from src.policy.engine import PolicyEngine
from src.policy.rules import DEFAULT_POLICY
from src.detection.card_testing import CardTestingDetector
from src.detection.velocity import VelocityAttackDetector
from src.detection.geo import GeoAnomalyDetector
from src.detection.bot import BotDetector
from src.detection.detector import DetectionResult
from src.scoring.risk_scorer import RiskScorer
from src.scoring.friendly_fraud import FriendlyFraudScorer, SubscriptionAbuseScorer
from src.api.auth import _extract_token
from src.metrics.telemetry import DecisionTelemetry, telemetry
from src.utils.logger import get_logger
from src.features.velocity import VelocityCounter
from src.features.store import FeatureStore
from src.evidence.service import EvidenceService
from src.config import settings


def _fresh_settings(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "testpw")
    settings_module = importlib.import_module("src.config.settings")
    Settings = settings_module.Settings
    return Settings()


def _minimal_event() -> PaymentEvent:
    return PaymentEvent(
        transaction_id=f"txn_{uuid.uuid4().hex[:8]}",
        idempotency_key=f"idem_{uuid.uuid4().hex[:8]}",
        amount_cents=100,
        card_token="card_123",
        service_id="svc_001",
    )


# =============================================================================
# Unit Sanity Tests
# =============================================================================


@pytest.mark.sanity
@pytest.mark.unit
class TestConfigSanity:
    def test_settings_class_importable(self, monkeypatch):
        settings_obj = _fresh_settings(monkeypatch)
        assert hasattr(settings_obj, "redis_host")
        assert hasattr(settings_obj, "postgres_host")
        assert hasattr(settings_obj, "api_token")

    def test_settings_has_expected_fields(self, monkeypatch):
        settings_obj = _fresh_settings(monkeypatch)
        fields = settings_obj.__class__.model_fields
        assert len(fields) >= 30
        for key in ("redis_host", "postgres_host", "metrics_enabled", "api_port"):
            assert key in fields

    def test_settings_defaults_valid(self, monkeypatch):
        settings_obj = _fresh_settings(monkeypatch)
        assert settings_obj.app_env == "development"
        assert settings_obj.redis_port == 6379
        assert settings_obj.target_e2e_latency_ms == 200

    def test_settings_computed_redis_url(self, monkeypatch):
        settings_obj = _fresh_settings(monkeypatch)
        assert settings_obj.redis_url.startswith("redis://")

    def test_settings_computed_postgres_url(self, monkeypatch):
        settings_obj = _fresh_settings(monkeypatch)
        assert "postgresql+asyncpg://" in settings_obj.postgres_url


@pytest.mark.sanity
@pytest.mark.unit
class TestSchemasSanity:
    def test_payment_event_minimal_valid(self):
        event = _minimal_event()
        assert event.transaction_id

    def test_payment_event_full_valid(self):
        event = PaymentEvent(
            transaction_id=f"txn_{uuid.uuid4().hex[:8]}",
            idempotency_key=f"idem_{uuid.uuid4().hex[:8]}",
            amount_cents=2500,
            currency="USD",
            card_token="card_abc",
            card_bin="411111",
            card_last_four="1234",
            card_country="US",
            service_id="mobile_prepaid_001",
            service_name="Telco Prepaid",
            service_type="mobile",
            event_subtype="topup",
            user_id="user_123",
            account_age_days=10,
            device=DeviceInfo(
                device_id="dev_1",
                device_type="mobile",
                os="iOS",
                os_version="17",
                browser="Safari",
                browser_version="17",
                is_emulator=False,
                is_rooted=False,
            ),
            geo=GeoInfo(
                ip_address="192.0.2.10",
                country_code="US",
                region="CA",
                city="San Francisco",
                latitude=37.77,
                longitude=-122.41,
                is_vpn=False,
                is_proxy=False,
                is_datacenter=False,
                is_tor=False,
            ),
            verification=VerificationInfo(
                avs_result="Y",
                cvv_result="M",
                three_ds_result="Y",
                three_ds_version="2.2",
            ),
        )
        assert event.card_token == "card_abc"

    def test_payment_event_rejects_invalid(self):
        with pytest.raises(ValidationError):
            PaymentEvent()

    def test_decision_enum_values(self):
        values = {item.value for item in Decision}
        assert values == {"ALLOW", "FRICTION", "REVIEW", "BLOCK"}

    def test_risk_scores_range_validation(self):
        with pytest.raises(ValidationError):
            RiskScores(risk_score=1.5)

    def test_velocity_features_defaults(self):
        features = VelocityFeatures()
        assert features.card_attempts_10m == 0
        assert features.user_transactions_24h == 0

    def test_feature_set_defaults(self):
        feature_set = FeatureSet()
        assert feature_set.velocity is not None
        assert feature_set.entity is not None


@pytest.mark.sanity
@pytest.mark.unit
class TestPolicyEngineSanity:
    def test_policy_engine_loads_default(self):
        engine = PolicyEngine()
        assert engine.version
        assert engine.hash

    def test_policy_engine_loads_yaml(self):
        engine = PolicyEngine(policy_path=Path("config/policy.yaml"))
        assert engine.policy is not None

    def test_default_policy_has_thresholds(self):
        assert DEFAULT_POLICY.thresholds is not None
        thresholds = DEFAULT_POLICY.thresholds
        if hasattr(thresholds, "risk"):
            assert thresholds.risk is not None
        else:
            assert "risk" in thresholds

    def test_default_policy_has_rules(self):
        assert len(DEFAULT_POLICY.rules) >= 3

    def test_policy_evaluate_returns_tuple(self):
        engine = PolicyEngine()
        event = _minimal_event()
        features = FeatureSet(amount_cents=event.amount_cents)
        scores = RiskScores(risk_score=0.1)
        decision, reasons, friction_type, review_priority = engine.evaluate(event, features, scores)
        assert decision in Decision
        assert isinstance(reasons, list)
        assert friction_type in (None, "3DS", "OTP", "STEP_UP", "CAPTCHA")
        assert review_priority in (None, "LOW", "MEDIUM", "HIGH", "URGENT")


@pytest.mark.sanity
@pytest.mark.unit
class TestDetectorsSanity:
    def test_card_testing_detector_instantiates(self):
        detector = CardTestingDetector()
        assert detector.velocity_threshold > 0

    def test_velocity_attack_detector_instantiates(self):
        detector = VelocityAttackDetector()
        assert detector.card_attempts_1h > 0

    def test_geo_anomaly_detector_instantiates(self):
        detector = GeoAnomalyDetector()
        assert detector.high_risk_countries

    def test_bot_detector_instantiates(self):
        detector = BotDetector()
        assert callable(detector.detect)

    @pytest.mark.asyncio
    async def test_all_detectors_return_detection_result(self):
        event = _minimal_event()
        features = FeatureSet(amount_cents=event.amount_cents)
        detectors = [
            CardTestingDetector(),
            VelocityAttackDetector(),
            GeoAnomalyDetector(),
            BotDetector(),
        ]
        for detector in detectors:
            result = await detector.detect(event, features)
            assert isinstance(result, DetectionResult)
            assert 0.0 <= result.score <= 1.0


@pytest.mark.sanity
@pytest.mark.unit
class TestScorersSanity:
    def test_risk_scorer_instantiates(self):
        scorer = RiskScorer()
        assert scorer.card_testing is not None
        assert scorer.detection_engine is not None

    @pytest.mark.asyncio
    async def test_risk_scorer_compute_returns_tuple(self):
        scorer = RiskScorer()
        event = _minimal_event()
        features = FeatureSet(amount_cents=event.amount_cents)
        scores, reasons = await scorer.compute_scores(event, features)
        assert isinstance(scores, RiskScores)
        assert isinstance(reasons, list)

    def test_friendly_fraud_scorer_instantiates(self):
        scorer = FriendlyFraudScorer()
        assert callable(scorer.score)

    def test_subscription_abuse_scorer_instantiates(self):
        scorer = SubscriptionAbuseScorer()
        assert callable(scorer.score)


@pytest.mark.sanity
@pytest.mark.unit
class TestAuthSanity:
    def test_extract_token_from_x_api_key(self):
        assert _extract_token(None, "abc") == "abc"

    def test_extract_token_from_bearer(self):
        assert _extract_token("Bearer token123", None) == "token123"

    def test_extract_token_none_when_empty(self):
        assert _extract_token(None, None) is None

    def test_extract_token_prefers_x_api_key(self):
        assert _extract_token("Bearer other", "preferred") == "preferred"


@pytest.mark.sanity
@pytest.mark.unit
class TestTelemetrySanity:
    def test_telemetry_creates(self):
        telemetry_instance = DecisionTelemetry(maxlen=100)
        assert telemetry_instance is not None

    def test_telemetry_record_and_snapshot(self):
        telemetry_instance = DecisionTelemetry(maxlen=10)
        telemetry_instance.record("ALLOW", 12.3)
        snapshot = telemetry_instance.snapshot(hours=1)
        assert snapshot["counts"]["ALLOW"] == 1
        assert snapshot["avg_latency_ms"] is not None

    def test_telemetry_ring_buffer_overflow(self):
        telemetry_instance = DecisionTelemetry(maxlen=3)
        for i in range(5):
            telemetry_instance.record("ALLOW", float(i))
        snapshot = telemetry_instance.snapshot(hours=1)
        assert len(snapshot["events"]) == 3

    def test_telemetry_module_singleton(self):
        assert telemetry is not None


@pytest.mark.sanity
@pytest.mark.unit
class TestLoggerSanity:
    def test_get_logger_returns_logger(self):
        logger = get_logger("sanity")
        assert logger.name == "sanity"

    def test_detection_result_dataclass(self):
        result = DetectionResult()
        assert result.score == 0.0
        assert result.triggered is False
        assert result.reasons == []


# =============================================================================
# Integration Sanity Tests
# =============================================================================


@pytest.mark.sanity
@pytest.mark.integration
class TestRedisIntegration:
    @pytest.mark.asyncio
    async def test_redis_ping(self, redis_client):
        assert await redis_client.ping() is True

    @pytest.mark.asyncio
    async def test_redis_set_get(self, redis_client):
        key = "fraud:sanity:set_get"
        try:
            await redis_client.set(key, "value")
            assert await redis_client.get(key) == "value"
        finally:
            await redis_client.delete(key)

    @pytest.mark.asyncio
    async def test_redis_zadd_zcount(self, redis_client):
        key = "fraud:sanity:zset"
        try:
            await redis_client.zadd(key, {"event1": 1})
            await redis_client.zadd(key, {"event2": 2})
            count = await redis_client.zcount(key, 0, 5)
            assert count == 2
        finally:
            await redis_client.delete(key)

    @pytest.mark.asyncio
    async def test_redis_key_expiry(self, redis_client):
        key = "fraud:sanity:expire"
        await redis_client.set(key, "value", ex=1)
        await asyncio.sleep(1.2)
        assert await redis_client.get(key) is None

    @pytest.mark.asyncio
    async def test_redis_pipeline(self, redis_client):
        key = "fraud:sanity:pipeline"
        try:
            pipe = redis_client.pipeline()
            pipe.set(key, "v1")
            pipe.get(key)
            results = await pipe.execute()
            assert results[0] is True
            assert results[1] == "v1"
        finally:
            await redis_client.delete(key)


@pytest.mark.sanity
@pytest.mark.integration
class TestPostgresIntegration:
    @pytest.mark.asyncio
    async def test_postgres_connectivity(self, pg_connection):
        value = await pg_connection.fetchval("SELECT 1")
        assert value == 1

    @pytest.mark.asyncio
    async def test_all_tables_exist(self, pg_connection):
        rows = await pg_connection.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        table_names = {row["table_name"] for row in rows}
        expected = {
            "transaction_evidence",
            "evidence_vault",
            "idempotency_records",
            "chargebacks",
            "policy_versions",
            "policy_audit_log",
            "decision_metrics",
        }
        assert expected.issubset(table_names)

    @pytest.mark.asyncio
    async def test_evidence_table_has_critical_columns(self, pg_connection):
        rows = await pg_connection.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='transaction_evidence'"
        )
        columns = {row["column_name"] for row in rows}
        expected = {
            "transaction_id",
            "risk_score",
            "decision",
            "features_snapshot",
            "processing_time_ms",
            "service_id",
        }
        assert expected.issubset(columns)

    @pytest.mark.asyncio
    async def test_key_indexes_exist(self, pg_connection):
        rows = await pg_connection.fetch(
            "SELECT indexname FROM pg_indexes WHERE tablename='transaction_evidence'"
        )
        indexes = {row["indexname"] for row in rows}
        for name in (
            "idx_evidence_card_token",
            "idx_evidence_captured_at",
            "idx_evidence_decision",
        ):
            assert name in indexes


@pytest.mark.sanity
@pytest.mark.integration
class TestVelocityCounterIntegration:
    @pytest.mark.asyncio
    async def test_increment_and_count(self, redis_client):
        counter = VelocityCounter(redis_client, key_prefix="fraud:sanity:")
        await counter.increment("card", "c1", "attempts", "tx1")
        count = await counter.count("card", "c1", "attempts", window_seconds=60)
        assert count >= 1
        await redis_client.delete("fraud:sanity:card:c1:attempts")

    @pytest.mark.asyncio
    async def test_count_distinct(self, redis_client):
        counter = VelocityCounter(redis_client, key_prefix="fraud:sanity:")
        await counter.add_distinct("card", "c1", "ips", "ip1")
        await counter.add_distinct("card", "c1", "ips", "ip2")
        count = await counter.count_distinct("card", "c1", "ips", window_seconds=60)
        assert count >= 2
        await redis_client.delete("fraud:sanity:card:c1:ips")

    @pytest.mark.asyncio
    async def test_key_prefix_applied(self, redis_client):
        counter = VelocityCounter(redis_client, key_prefix="fraud:sanity:")
        await counter.increment("user", "u1", "transactions", "tx1")
        keys = await redis_client.keys("fraud:sanity:*")
        assert any(key.startswith("fraud:sanity:") for key in keys)
        if keys:
            await redis_client.delete(*keys)


@pytest.mark.sanity
@pytest.mark.integration
class TestFeatureStoreIntegration:
    @pytest.mark.asyncio
    async def test_compute_velocity_features(self, redis_client, sample_event, monkeypatch):
        monkeypatch.setattr(settings, "redis_key_prefix", "fraud:sanity:")
        store = FeatureStore(redis_client)
        features = await store.compute_velocity_features(sample_event)
        assert isinstance(features, VelocityFeatures)

    @pytest.mark.asyncio
    async def test_compute_features_returns_feature_set(self, redis_client, sample_event, monkeypatch):
        monkeypatch.setattr(settings, "redis_key_prefix", "fraud:sanity:")
        store = FeatureStore(redis_client)
        features = await store.compute_features(sample_event)
        assert isinstance(features, FeatureSet)

    @pytest.mark.asyncio
    async def test_update_entity_profiles(self, redis_client, sample_event, monkeypatch):
        monkeypatch.setattr(settings, "redis_key_prefix", "fraud:sanity:")
        store = FeatureStore(redis_client)
        await store.update_entity_profiles(sample_event, is_decline=False)
        key = f"fraud:sanity:profile:card:{sample_event.card_token}"
        data = await redis_client.hgetall(key)
        assert "total_transactions" in data
        keys = await redis_client.keys("fraud:sanity:*")
        if keys:
            await redis_client.delete(*keys)


@pytest.mark.sanity
@pytest.mark.integration
class TestEvidenceIntegration:
    @pytest.mark.asyncio
    async def test_evidence_service_health_check(self, pg_connection):
        service = EvidenceService(settings.postgres_url)
        await service.initialize()
        assert await service.health_check() is True
        await service.close()

    @pytest.mark.asyncio
    async def test_idempotency_store_retrieve(self, pg_connection):
        service = EvidenceService(settings.postgres_url)
        await service.initialize()
        key = f"idem_{uuid.uuid4().hex[:8]}"
        payload = {"transaction_id": "txn_test", "decision": "ALLOW"}
        await service.store_idempotency_response(key, payload, ttl_hours=1)
        stored = await service.get_idempotency_response(key)
        assert stored["transaction_id"] == "txn_test"
        await pg_connection.execute(
            "DELETE FROM idempotency_records WHERE idempotency_key = $1",
            key,
        )
        await service.close()

    @pytest.mark.asyncio
    async def test_capture_and_get_evidence(self, pg_connection, sample_event):
        service = EvidenceService(settings.postgres_url)
        await service.initialize()
        features = FeatureSet(amount_cents=sample_event.amount_cents)
        scores = RiskScores(risk_score=0.05)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.ALLOW,
            scores=scores,
        )
        evidence_id = await service.capture_evidence(sample_event, features, scores, response)
        assert evidence_id is not None
        record = await service.get_evidence(sample_event.transaction_id)
        assert record is not None
        await pg_connection.execute(
            "DELETE FROM evidence_vault WHERE evidence_id = $1",
            evidence_id,
        )
        await pg_connection.execute(
            "DELETE FROM transaction_evidence WHERE id = $1",
            evidence_id,
        )
        await service.close()


# =============================================================================
# System / E2E Sanity Tests
# =============================================================================


@pytest.mark.sanity
@pytest.mark.system
class TestHealthSystem:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, system_client, check_api_available):
        resp = await system_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_all_components_present(self, system_client, check_api_available):
        resp = await system_client.get("/health")
        data = resp.json()
        assert "components" in data
        for key in ("redis", "postgres", "policy"):
            assert key in data["components"]

    @pytest.mark.asyncio
    async def test_health_status_healthy(self, system_client, check_api_available):
        resp = await system_client.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.sanity
@pytest.mark.system
class TestDecisionSystem:
    @pytest.mark.asyncio
    async def test_clean_transaction_allowed(
        self, system_client, check_api_available, sanity_headers, clean_transaction_payload
    ):
        resp = await system_client.post("/decide", json=clean_transaction_payload, headers=sanity_headers)
        assert resp.status_code == 200
        assert resp.json()["decision"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_high_risk_blocked_or_reviewed(
        self, system_client, check_api_available, sanity_headers, high_risk_transaction_payload
    ):
        resp = await system_client.post("/decide", json=high_risk_transaction_payload, headers=sanity_headers)
        assert resp.status_code == 200
        assert resp.json()["decision"] in {"BLOCK", "REVIEW"}

    @pytest.mark.asyncio
    async def test_idempotency_caching(
        self, system_client, check_api_available, sanity_headers, clean_transaction_payload
    ):
        resp1 = await system_client.post("/decide", json=clean_transaction_payload, headers=sanity_headers)
        resp2 = await system_client.post("/decide", json=clean_transaction_payload, headers=sanity_headers)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json().get("is_cached") is True

    @pytest.mark.asyncio
    async def test_invalid_request_422(self, system_client, check_api_available):
        resp = await system_client.post("/decide", json={})
        assert resp.status_code == 422


@pytest.mark.sanity
@pytest.mark.system
class TestAuthSystem:
    @pytest.mark.asyncio
    async def test_wrong_token_401(
        self, system_client, check_api_available, clean_transaction_payload, sanity_api_token
    ):
        if not sanity_api_token:
            pytest.skip("Auth not configured")
        resp = await system_client.post(
            "/decide",
            json=clean_transaction_payload,
            headers={"X-API-Key": "bad-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_correct_token_200(
        self, system_client, check_api_available, sanity_headers, sanity_api_token
    ):
        if not sanity_api_token:
            pytest.skip("Auth not configured")
        resp = await system_client.get("/policy/version", headers=sanity_headers)
        assert resp.status_code == 200


@pytest.mark.sanity
@pytest.mark.system
class TestPolicySystem:
    @pytest.mark.asyncio
    async def test_get_policy_version(self, system_client, check_api_available, sanity_headers):
        resp = await system_client.get("/policy/version", headers=sanity_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "hash" in data

    @pytest.mark.asyncio
    async def test_get_full_policy(self, system_client, check_api_available, sanity_headers):
        resp = await system_client.get("/policy", headers=sanity_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "policy" in data
        assert "thresholds" in data["policy"]
        assert "rules" in data["policy"]


@pytest.mark.sanity
@pytest.mark.system
class TestDashboardSystem:
    @pytest.mark.asyncio
    async def test_dashboard_accessible(self, sanity_dashboard_url, sanity_headers):
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(sanity_dashboard_url, headers=sanity_headers)
            assert resp.status_code == 200
            assert "Streamlit" in resp.text

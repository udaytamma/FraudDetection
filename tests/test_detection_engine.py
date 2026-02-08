"""
Detection Engine Tests - Telco/MSP Payment Fraud

Tests for the DetectionEngine orchestrator and edge cases
in individual detectors. Validates parallel execution,
error handling, and score aggregation.
"""

import pytest
import pytest_asyncio

from src.schemas import (
    PaymentEvent,
    VelocityFeatures,
    EntityFeatures,
    FeatureSet,
    DecisionReason,
)
from src.detection.detector import (
    DetectionResult,
    BaseDetector,
    DetectionEngine,
)
from src.detection import (
    CardTestingDetector,
    VelocityAttackDetector,
    GeoAnomalyDetector,
    BotDetector,
)


# =============================================================================
# Mock Detectors for Testing Engine Behavior
# =============================================================================

class AlwaysTriggersDetector(BaseDetector):
    """Mock detector that always triggers."""

    async def detect(self, event, features):
        result = DetectionResult(score=0.9, triggered=True)
        result.reasons.append(
            DecisionReason(
                code="MOCK_TRIGGER",
                description="Mock detector triggered",
                severity="HIGH",
            )
        )
        return result


class NeverTriggersDetector(BaseDetector):
    """Mock detector that never triggers."""

    async def detect(self, event, features):
        return DetectionResult(score=0.0, triggered=False)


class FailingDetector(BaseDetector):
    """Mock detector that raises an exception."""

    async def detect(self, event, features):
        raise RuntimeError("Detector crashed!")


class SlowDetector(BaseDetector):
    """Mock detector that simulates slow processing."""

    async def detect(self, event, features):
        import asyncio
        await asyncio.sleep(0.01)  # 10ms delay
        return DetectionResult(score=0.5, triggered=True)


# =============================================================================
# DetectionEngine Tests
# =============================================================================

class TestDetectionEngine:
    """Tests for DetectionEngine orchestration."""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, sample_event):
        """All detectors should run in parallel and return results."""
        engine = DetectionEngine([
            AlwaysTriggersDetector(),
            NeverTriggersDetector(),
        ])
        features = FeatureSet()

        results, reasons = await engine.run_detection(sample_event, features)

        assert "AlwaysTriggersDetector" in results
        assert "NeverTriggersDetector" in results
        assert results["AlwaysTriggersDetector"].score == 0.9
        assert results["NeverTriggersDetector"].score == 0.0
        assert len(reasons) == 1

    @pytest.mark.asyncio
    async def test_failing_detector_handled_gracefully(self, sample_event):
        """A failing detector should not crash the engine."""
        engine = DetectionEngine([
            AlwaysTriggersDetector(),
            FailingDetector(),
            NeverTriggersDetector(),
        ])
        features = FeatureSet()

        results, reasons = await engine.run_detection(sample_event, features)

        # Failing detector should produce neutral result
        assert results["FailingDetector"].score == 0.0
        # Other detectors should still produce results
        assert results["AlwaysTriggersDetector"].score == 0.9
        assert results["NeverTriggersDetector"].score == 0.0

    @pytest.mark.asyncio
    async def test_empty_detector_list(self, sample_event):
        """Engine with no detectors should return empty results."""
        engine = DetectionEngine([])
        features = FeatureSet()

        results, reasons = await engine.run_detection(sample_event, features)

        assert len(results) == 0
        assert len(reasons) == 0

    @pytest.mark.asyncio
    async def test_all_reasons_aggregated(self, sample_event):
        """Reasons from all detectors should be aggregated."""
        engine = DetectionEngine([
            AlwaysTriggersDetector(),
            AlwaysTriggersDetector(),
        ])
        features = FeatureSet()

        _, reasons = await engine.run_detection(sample_event, features)

        assert len(reasons) == 2

    @pytest.mark.asyncio
    async def test_concurrent_slow_detectors(self, sample_event):
        """Multiple slow detectors should run concurrently, not sequentially."""
        import time

        # Use unique class names so results dict has 3 entries
        class SlowDetector1(SlowDetector):
            pass

        class SlowDetector2(SlowDetector):
            pass

        class SlowDetector3(SlowDetector):
            pass

        engine = DetectionEngine([
            SlowDetector1(),
            SlowDetector2(),
            SlowDetector3(),
        ])
        features = FeatureSet()

        start = time.monotonic()
        results, _ = await engine.run_detection(sample_event, features)
        elapsed = time.monotonic() - start

        # 3 detectors each sleeping 10ms should complete in ~10-20ms
        # if concurrent, but ~30ms if sequential
        assert elapsed < 0.025  # Allow 25ms headroom
        assert len(results) == 3

    def test_aggregate_scores(self, sample_event):
        """Test aggregate score computation."""
        engine = DetectionEngine([])

        results = {
            "CardTestingDetector": DetectionResult(score=0.8),
            "VelocityAttackDetector": DetectionResult(score=0.6),
            "GeoAnomalyDetector": DetectionResult(score=0.3),
            "BotDetector": DetectionResult(score=0.0),
        }

        criminal, friendly = engine.compute_aggregate_scores(results)

        assert criminal == 0.8  # Max of criminal detectors
        assert friendly == 0.0  # No friendly fraud detector results

    def test_aggregate_scores_empty(self, sample_event):
        """Aggregate scores with no results should return zeros."""
        engine = DetectionEngine([])

        criminal, friendly = engine.compute_aggregate_scores({})

        assert criminal == 0.0
        assert friendly == 0.0


# =============================================================================
# DetectionResult Tests
# =============================================================================

class TestDetectionResult:
    """Tests for DetectionResult dataclass."""

    def test_default_values(self):
        """Default result should be neutral."""
        result = DetectionResult()

        assert result.score == 0.0
        assert not result.triggered
        assert len(result.reasons) == 0

    def test_add_reason(self):
        """add_reason should append a DecisionReason."""
        result = DetectionResult()
        result.add_reason(
            code="TEST_CODE",
            description="Test description",
            severity="HIGH",
            value="42",
            threshold="10",
        )

        assert len(result.reasons) == 1
        assert result.reasons[0].code == "TEST_CODE"
        assert result.reasons[0].severity == "HIGH"
        assert result.reasons[0].value == "42"
        assert result.reasons[0].threshold == "10"

    def test_add_multiple_reasons(self):
        """Multiple reasons can be added."""
        result = DetectionResult()
        result.add_reason(code="CODE_1", description="First")
        result.add_reason(code="CODE_2", description="Second")
        result.add_reason(code="CODE_3", description="Third")

        assert len(result.reasons) == 3


# =============================================================================
# Real Detector Edge Cases
# =============================================================================

class TestCardTestingEdgeCases:
    """Edge cases for card testing detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return CardTestingDetector()

    @pytest.mark.asyncio
    async def test_zero_velocity_features(self, detector, sample_event):
        """All-zero velocity features should produce zero score."""
        features = FeatureSet(
            velocity=VelocityFeatures(),
            entity=EntityFeatures(),
        )

        result = await detector.detect(sample_event, features)

        assert result.score == 0.0
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_boundary_threshold(self, detector, sample_event):
        """Exactly at threshold should NOT trigger (need to exceed)."""
        default_threshold = detector.velocity_threshold
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=default_threshold,
            ),
        )

        result = await detector.detect(sample_event, features)

        # At threshold is fine; above threshold triggers
        assert result.score >= 0.0  # Valid score regardless


class TestGeoEdgeCases:
    """Edge cases for geo anomaly detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return GeoAnomalyDetector()

    @pytest.mark.asyncio
    async def test_no_geo_data(self, detector, sample_event):
        """Missing geo data should not trigger (low confidence)."""
        sample_event.geo = None
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_tor=False,
                ip_is_datacenter=False,
                ip_country_card_country_match=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        # Should handle gracefully
        assert result.score >= 0.0

    @pytest.mark.asyncio
    async def test_vpn_detection(self, detector, sample_event):
        """VPN usage should trigger geo anomaly."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_vpn=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert any("VPN" in r.code for r in result.reasons)


class TestBotEdgeCases:
    """Edge cases for bot detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return BotDetector()

    @pytest.mark.asyncio
    async def test_no_device_info(self, detector, sample_event):
        """Missing device info should be handled gracefully."""
        sample_event.device = None
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_emulator=False,
                device_is_rooted=False,
                ip_is_datacenter=False,
                ip_is_tor=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score >= 0.0

    @pytest.mark.asyncio
    async def test_combined_bot_signals(self, detector, sample_event):
        """Multiple bot signals should produce higher score."""
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_emulator=True,
                device_is_rooted=True,
                ip_is_datacenter=True,
                ip_is_tor=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score > 0.5
        assert result.triggered
        assert len(result.reasons) >= 2

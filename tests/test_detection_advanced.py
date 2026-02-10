"""
Advanced Detection Tests - Telco/MSP Payment Fraud

Tests for additional bot detection branches,
velocity attack edge cases, and card testing device/IP checks.
Covers uncovered code paths in detection modules.
"""

import pytest
import pytest_asyncio

from src.schemas import (
    PaymentEvent,
    VelocityFeatures,
    EntityFeatures,
    FeatureSet,
    DeviceInfo,
    GeoInfo,
)
from src.detection import (
    CardTestingDetector,
    VelocityAttackDetector,
    GeoAnomalyDetector,
    BotDetector,
)

# =============================================================================
# CardTestingDetector - Device/IP Card Coverage
# =============================================================================

class TestCardTestingDeviceIP:
    """Tests for card testing device/IP card checks (Check 4)."""

    @pytest_asyncio.fixture
    def detector(self):
        return CardTestingDetector(
            velocity_threshold_10m=5,
            decline_ratio_threshold=0.8,
        )

    @pytest.mark.asyncio
    async def test_device_many_cards_triggers(self, detector, sample_event):
        """Device using 5+ cards in 1 hour should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                device_distinct_cards_1h=7,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("DEVICE_CARDS" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_ip_many_cards_triggers(self, detector, sample_event):
        """IP using 10+ cards in 1 hour should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                ip_distinct_cards_1h=12,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("IP_CARDS" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_combined_velocity_and_ip_cards(self, detector, sample_event):
        """Multiple signals should produce compounded score."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=10,
                card_declines_10m=8,
                device_distinct_cards_1h=6,
                ip_distinct_cards_1h=15,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score > 0.8  # Multiple strong signals
        assert len(result.reasons) >= 3


# =============================================================================
# BotDetector - Branch Coverage for Event-Level Signals
# =============================================================================

class TestBotEventLevelSignals:
    """Tests for bot detection from event.device/event.geo (not just entity features)."""

    @pytest_asyncio.fixture
    def detector(self):
        return BotDetector()

    @pytest.mark.asyncio
    async def test_event_emulator_when_entity_not_flagged(self, detector, sample_event):
        """Event-level emulator flag should trigger even when entity features miss it."""
        sample_event.device.is_emulator = True
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_emulator=False,  # Entity doesn't know
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("EMULATOR" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_event_rooted_when_entity_not_flagged(self, detector, sample_event):
        """Event-level rooted flag should trigger even when entity features miss it."""
        sample_event.device.is_rooted = True
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_rooted=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert any("ROOTED" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_event_datacenter_when_entity_not_flagged(self, detector, sample_event):
        """Event-level datacenter flag should trigger from geo info."""
        sample_event.geo.is_datacenter = True
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_datacenter=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert any("DATACENTER" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_event_tor_when_entity_not_flagged(self, detector, sample_event):
        """Event-level tor flag should trigger from geo info."""
        sample_event.geo.is_tor = True
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_tor=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert any("TOR" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_suspicious_user_agent_linux_safari(self, detector, sample_event):
        """Safari on Linux is suspicious (Safari doesn't run on Linux)."""
        sample_event.device.browser = "Safari"
        sample_event.device.os = "Linux"
        features = FeatureSet()

        result = await detector.detect(sample_event, features)

        assert any("SUSPICIOUS_UA" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_suspicious_user_agent_windows_mobile(self, detector, sample_event):
        """Windows on mobile device type is suspicious."""
        sample_event.device.os = "Windows"
        sample_event.device.device_type = "mobile"
        features = FeatureSet()

        result = await detector.detect(sample_event, features)

        assert any("SUSPICIOUS_UA" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_incomplete_fingerprint(self, detector, sample_event):
        """Device with many missing fingerprint fields should trigger."""
        sample_event.device.os = None
        sample_event.device.browser = None
        sample_event.device.screen_resolution = None
        sample_event.device.timezone = None
        sample_event.device.language = None
        features = FeatureSet()

        result = await detector.detect(sample_event, features)

        assert any("INCOMPLETE_FINGERPRINT" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_missing_device_id_incomplete(self, detector, sample_event):
        """Device with no device_id should be flagged as incomplete."""
        sample_event.device.device_id = None
        features = FeatureSet()

        result = await detector.detect(sample_event, features)

        assert any("INCOMPLETE_FINGERPRINT" in r.code for r in result.reasons)


# =============================================================================
# VelocityAttackDetector - Additional Branch Coverage
# =============================================================================

class TestVelocityAdditionalBranches:
    """Tests for uncovered velocity attack branches."""

    @pytest_asyncio.fixture
    def detector(self):
        return VelocityAttackDetector()

    @pytest.mark.asyncio
    async def test_ip_many_cards_triggers(self, detector, sample_event):
        """IP with many distinct cards should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                ip_distinct_cards_1h=15,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("IP_CARDS" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_user_high_velocity(self, detector, sample_event):
        """User with very high transaction count should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                user_transactions_24h=50,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score > 0

    @pytest.mark.asyncio
    async def test_user_high_amount_velocity(self, detector, sample_event):
        """User with very high spend in 24h should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                user_amount_24h_cents=500000,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score > 0


# =============================================================================
# GeoAnomalyDetector - Additional Branch Coverage
# =============================================================================

class TestGeoAdditionalBranches:
    """Tests for uncovered geo anomaly branches."""

    @pytest_asyncio.fixture
    def detector(self):
        return GeoAnomalyDetector()

    @pytest.mark.asyncio
    async def test_high_risk_country(self, detector, sample_event):
        """Transaction from high-risk country should trigger."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_country_code="NG",
                ip_country_card_country_match=False,
            ),
        )
        sample_event.card_country = "US"

        result = await detector.detect(sample_event, features)

        assert result.score > 0
        assert any("COUNTRY" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_proxy_detection(self, detector, sample_event):
        """Proxy IP should trigger geo anomaly."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_proxy=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        # Check for VPN/proxy related reason
        assert result.score > 0

"""
Detection Module Tests

Tests for fraud detection logic.
"""

import pytest
import pytest_asyncio

from src.schemas import PaymentEvent, VelocityFeatures, EntityFeatures, FeatureSet
from src.detection import (
    CardTestingDetector,
    VelocityAttackDetector,
    GeoAnomalyDetector,
    BotDetector,
)


class TestCardTestingDetector:
    """Tests for card testing detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return CardTestingDetector(
            velocity_threshold_10m=5,
            decline_ratio_threshold=0.8,
        )

    @pytest.mark.asyncio
    async def test_normal_transaction(self, detector, sample_event):
        """Test that normal transactions don't trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=1,
                card_declines_10m=0,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score < 0.5
        assert not result.triggered
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_high_velocity_triggers(self, detector, sample_event):
        """Test that high velocity triggers detection."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=10,  # Above threshold
                card_declines_10m=0,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score >= 0.5
        assert result.triggered
        assert any("VELOCITY" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_high_decline_ratio_triggers(self, detector, sample_event):
        """Test that high decline ratio triggers detection."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=5,
                card_declines_10m=4,  # 80% decline rate
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score >= 0.5
        assert result.triggered
        assert any("DECLINE_RATIO" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_small_amount_with_velocity(self, detector, card_testing_event):
        """Test small amount combined with velocity pattern."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=3,
                card_declines_10m=1,
            ),
        )

        result = await detector.detect(card_testing_event, features)

        # Small amount alone shouldn't trigger, but with velocity it should
        assert any("SMALL_AMOUNTS" in r.code for r in result.reasons)


class TestVelocityAttackDetector:
    """Tests for velocity attack detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return VelocityAttackDetector(
            card_attempts_1h_threshold=10,
            device_cards_24h_threshold=5,
            ip_cards_1h_threshold=10,
        )

    @pytest.mark.asyncio
    async def test_normal_velocity(self, detector, sample_event):
        """Test normal velocity doesn't trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_1h=2,
                device_distinct_cards_24h=1,
                ip_distinct_cards_1h=1,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score < 0.4
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_card_velocity_attack(self, detector, sample_event):
        """Test card velocity attack detection."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_1h=15,  # Above threshold
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("CARD_1H" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_device_card_attack(self, detector, sample_event):
        """Test device with many cards detection."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                device_distinct_cards_24h=8,  # Above threshold
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("DEVICE_CARDS" in r.code for r in result.reasons)


class TestGeoAnomalyDetector:
    """Tests for geographic anomaly detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return GeoAnomalyDetector()

    @pytest.mark.asyncio
    async def test_normal_geo(self, detector, sample_event):
        """Test normal geo doesn't trigger."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_country_card_country_match=True,
                ip_is_tor=False,
                ip_is_datacenter=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score < 0.4

    @pytest.mark.asyncio
    async def test_tor_triggers(self, detector, sample_event):
        """Test Tor exit node triggers."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_tor=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("TOR" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_datacenter_ip_triggers(self, detector, sample_event):
        """Test datacenter IP triggers."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_is_datacenter=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("DATACENTER" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_country_mismatch(self, detector, sample_event):
        """Test country mismatch triggers."""
        features = FeatureSet(
            entity=EntityFeatures(
                ip_country_card_country_match=False,
                ip_country_code="NG",
            ),
        )
        sample_event.card_country = "US"

        result = await detector.detect(sample_event, features)

        assert any("COUNTRY" in r.code for r in result.reasons)


class TestBotDetector:
    """Tests for bot/automation detection."""

    @pytest_asyncio.fixture
    def detector(self):
        return BotDetector()

    @pytest.mark.asyncio
    async def test_normal_device(self, detector, sample_event):
        """Test normal device doesn't trigger."""
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_emulator=False,
                device_is_rooted=False,
                ip_is_datacenter=False,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.score < 0.5

    @pytest.mark.asyncio
    async def test_emulator_triggers(self, detector, sample_event):
        """Test emulator detection."""
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_emulator=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert result.triggered
        assert any("EMULATOR" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_rooted_device(self, detector, sample_event):
        """Test rooted device detection."""
        features = FeatureSet(
            entity=EntityFeatures(
                device_is_rooted=True,
            ),
        )

        result = await detector.detect(sample_event, features)

        assert any("ROOTED" in r.code for r in result.reasons)

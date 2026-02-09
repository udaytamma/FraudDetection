"""
Scoring Module Tests - Telco/MSP Payment Fraud

Tests for risk scoring, high-value transaction scoring,
and friendly fraud scoring. All tests use mocked features
(no Redis/PostgreSQL required).
"""

import pytest
import pytest_asyncio

from src.schemas import (
    PaymentEvent,
    VelocityFeatures,
    EntityFeatures,
    FeatureSet,
    RiskScores,
    DecisionReason,
    ServiceType,
    EventSubtype,
)
from src.scoring.risk_scorer import RiskScorer, HighValueTransactionScorer
from src.scoring.friendly_fraud import FriendlyFraudScorer, SubscriptionAbuseScorer


class TestRiskScorer:
    """Tests for the main risk scoring engine."""

    @pytest_asyncio.fixture
    def scorer(self):
        return RiskScorer()

    @pytest.mark.asyncio
    async def test_clean_transaction_low_score(self, scorer, sample_event):
        """Clean transaction with no signals should produce low risk score."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=1,
                card_declines_10m=0,
                card_attempts_1h=2,
                device_distinct_cards_24h=1,
                ip_distinct_cards_1h=1,
            ),
            entity=EntityFeatures(
                card_is_new=False,
                card_total_transactions=50,
                user_is_new=False,
                user_is_guest=False,
                user_total_transactions=30,
                device_total_transactions=20,
                ip_is_tor=False,
                ip_is_datacenter=False,
                device_is_emulator=False,
                device_is_rooted=False,
                ip_country_card_country_match=True,
            ),
            amount_cents=2500,
            has_3ds=True,
            avs_match=True,
            cvv_match=True,
        )

        scores, reasons = await scorer.compute_scores(sample_event, features)

        assert isinstance(scores, RiskScores)
        assert scores.risk_score < 0.3
        assert scores.criminal_score < 0.3
        assert len(reasons) == 0

    @pytest.mark.asyncio
    async def test_high_risk_transaction_high_score(self, scorer, high_risk_event):
        """Transaction with multiple risk signals should produce high score."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=1,
                card_attempts_1h=2,
            ),
            entity=EntityFeatures(
                device_is_emulator=True,
                ip_is_datacenter=True,
                ip_is_tor=True,
                card_is_new=True,
                user_is_new=True,
                user_is_guest=False,
            ),
            amount_cents=120000,
        )

        scores, reasons = await scorer.compute_scores(high_risk_event, features)

        assert scores.risk_score >= 0.5
        assert scores.bot_score > 0
        assert len(reasons) > 0

    @pytest.mark.asyncio
    async def test_scores_bounded_zero_to_one(self, scorer, sample_event):
        """All scores should be in [0.0, 1.0] range."""
        features = FeatureSet(
            velocity=VelocityFeatures(
                card_attempts_10m=50,
                card_declines_10m=45,
                card_attempts_1h=100,
                device_distinct_cards_24h=20,
                ip_distinct_cards_1h=30,
            ),
            entity=EntityFeatures(
                device_is_emulator=True,
                device_is_rooted=True,
                ip_is_tor=True,
                ip_is_datacenter=True,
                ip_country_card_country_match=False,
                ip_country_code="NG",
                card_is_new=True,
                user_is_new=True,
            ),
        )

        scores, _ = await scorer.compute_scores(sample_event, features)

        assert 0.0 <= scores.risk_score <= 1.0
        assert 0.0 <= scores.criminal_score <= 1.0
        assert 0.0 <= scores.friendly_fraud_score <= 1.0
        assert 0.0 <= scores.confidence <= 1.0
        assert 0.0 <= scores.card_testing_score <= 1.0
        assert 0.0 <= scores.velocity_score <= 1.0
        assert 0.0 <= scores.geo_score <= 1.0
        assert 0.0 <= scores.bot_score <= 1.0

    @pytest.mark.asyncio
    async def test_confidence_high_with_history(self, scorer, sample_event):
        """Confidence should be high when entities have transaction history."""
        features = FeatureSet(
            entity=EntityFeatures(
                card_is_new=False,
                card_total_transactions=100,
                user_is_new=False,
                user_is_guest=False,
                user_total_transactions=50,
                device_total_transactions=30,
            ),
            has_3ds=True,
            amount_cents=2500,
        )

        scores, _ = await scorer.compute_scores(sample_event, features)

        assert scores.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_confidence_low_for_new_entities(self, scorer, sample_event):
        """Confidence should be low when all entities are new."""
        features = FeatureSet(
            entity=EntityFeatures(
                card_is_new=True,
                card_total_transactions=0,
                user_is_new=True,
                user_is_guest=True,
                user_total_transactions=0,
                device_total_transactions=0,
            ),
            amount_cents=2500,
        )

        scores, _ = await scorer.compute_scores(sample_event, features)

        assert scores.confidence <= 0.5

    @pytest.mark.asyncio
    async def test_friendly_fraud_signals_propagate(self, scorer, sample_event):
        """Friendly fraud signals should appear in the combined scores."""
        features = FeatureSet(
            entity=EntityFeatures(
                user_chargeback_count_90d=5,
                user_risk_tier="HIGH",
                card_chargeback_count=3,
                device_chargeback_count=2,
                card_is_new=False,
                card_total_transactions=20,
                user_is_new=False,
                user_is_guest=False,
                user_total_transactions=15,
            ),
            velocity=VelocityFeatures(
                user_transactions_24h=2,
            ),
            amount_cents=2500,
        )

        scores, reasons = await scorer.compute_scores(sample_event, features)

        assert scores.friendly_fraud_score > 0
        assert any("CHARGEBACK" in r.code or "RISK_TIER" in r.code for r in reasons)


class TestHighValueTransactionScorer:
    """Tests for high-value transaction scoring."""

    @pytest.fixture
    def scorer(self):
        return HighValueTransactionScorer(
            high_value_threshold_cents=100000,
            new_account_days=7,
        )

    def test_below_threshold_no_score(self, scorer, sample_event):
        """Transactions below threshold should not be scored."""
        features = FeatureSet(amount_cents=5000)

        score, reasons = scorer.score(sample_event, features)

        assert score == 0.0
        assert len(reasons) == 0

    def test_high_value_new_account(self, scorer, sample_event):
        """High-value from new/guest account should trigger."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=True,
                user_is_guest=False,
                card_is_new=False,
            ),
            has_3ds=True,
            avs_match=True,
            cvv_match=True,
        )

        score, reasons = scorer.score(sample_event, features)

        assert score > 0
        assert any("NEW_ACCOUNT" in r.code for r in reasons)

    def test_high_value_new_card(self, scorer, sample_event):
        """High-value with first-seen card should trigger."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=False,
                user_is_guest=False,
                card_is_new=True,
            ),
            has_3ds=True,
            avs_match=True,
            cvv_match=True,
        )

        score, reasons = scorer.score(sample_event, features)

        assert score > 0
        assert any("NEW_CARD" in r.code for r in reasons)

    def test_high_value_no_3ds(self, scorer, sample_event):
        """High-value without 3DS should trigger."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
            ),
            has_3ds=False,
            avs_match=True,
            cvv_match=True,
        )

        score, reasons = scorer.score(sample_event, features)

        assert score > 0
        assert any("NO_3DS" in r.code for r in reasons)

    def test_high_value_avs_mismatch(self, scorer, sample_event):
        """High-value with AVS mismatch should trigger."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
            ),
            has_3ds=True,
            avs_match=False,
            cvv_match=True,
        )

        score, reasons = scorer.score(sample_event, features)

        assert score > 0
        assert any("AVS" in r.code for r in reasons)

    def test_high_value_cvv_mismatch(self, scorer, sample_event):
        """High-value with CVV mismatch should trigger."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
            ),
            has_3ds=True,
            avs_match=True,
            cvv_match=False,
        )

        score, reasons = scorer.score(sample_event, features)

        assert score > 0
        assert any("CVV" in r.code for r in reasons)

    def test_multiple_signals_compound(self, scorer, sample_event):
        """Multiple signals should compound the score."""
        sample_event.amount_cents = 120000
        features = FeatureSet(
            amount_cents=120000,
            entity=EntityFeatures(
                user_is_new=True,
                user_is_guest=True,
                card_is_new=True,
            ),
            has_3ds=False,
            avs_match=False,
            cvv_match=False,
        )

        score, reasons = scorer.score(sample_event, features)

        # Multiple signals should produce a higher score than any single signal
        assert score > 0.6
        assert len(reasons) >= 3

    def test_score_capped_at_one(self, scorer, sample_event):
        """Score should never exceed 1.0 even with all signals."""
        sample_event.amount_cents = 200000
        features = FeatureSet(
            amount_cents=200000,
            entity=EntityFeatures(
                user_is_new=True,
                user_is_guest=True,
                card_is_new=True,
            ),
            has_3ds=False,
            avs_match=False,
            cvv_match=False,
        )

        score, _ = scorer.score(sample_event, features)

        assert score <= 1.0


class TestFriendlyFraudScorer:
    """Tests for friendly fraud scoring."""

    @pytest_asyncio.fixture
    def scorer(self):
        return FriendlyFraudScorer(
            chargeback_rate_threshold=0.03,
            high_chargeback_count_threshold=2,
            high_refund_count_threshold=5,
        )

    @pytest.mark.asyncio
    async def test_clean_user_no_score(self, scorer, sample_event):
        """User with no history flags should score zero."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=2),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score == 0.0
        assert not result.triggered
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_high_chargeback_rate_triggers(self, scorer, sample_event):
        """User with high chargeback rate should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_chargeback_count_90d=10,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("CHARGEBACK_RATE" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_absolute_chargeback_count_triggers(self, scorer, sample_event):
        """User exceeding chargeback count threshold should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=3,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("DISPUTE_HISTORY" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_high_refund_count_triggers(self, scorer, sample_event):
        """User with high refund count should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=8,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("REFUND" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_card_chargeback_history_triggers(self, scorer, sample_event):
        """Card with chargeback history should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=2,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("CARD_CHARGEBACK" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_device_chargeback_history_triggers(self, scorer, sample_event):
        """Device with chargeback history should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=3,
                user_risk_tier="NORMAL",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("DEVICE_CHARGEBACK" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_high_risk_tier_triggers(self, scorer, sample_event):
        """User in HIGH risk tier should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="HIGH",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("HIGH_RISK_TIER" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_elevated_risk_tier_triggers(self, scorer, sample_event):
        """User in ELEVATED risk tier should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="ELEVATED",
                user_is_guest=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("ELEVATED_RISK_TIER" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_guest_high_value_triggers(self, scorer, sample_event):
        """Guest user with high-value transaction should trigger."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=0),
            entity=EntityFeatures(
                user_chargeback_count_90d=0,
                user_refund_count_90d=0,
                card_chargeback_count=0,
                device_chargeback_count=0,
                user_risk_tier="NORMAL",
                user_is_guest=True,
            ),
            amount_cents=99900,
        )
        sample_event.amount_cents = 99900

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("GUEST_HIGH_VALUE" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_multiple_signals_compound(self, scorer, sample_event):
        """Multiple friendly fraud signals should compound score."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_chargeback_count_90d=5,
                user_refund_count_90d=10,
                card_chargeback_count=2,
                device_chargeback_count=3,
                user_risk_tier="HIGH",
                user_is_guest=True,
            ),
            amount_cents=99900,
        )
        sample_event.amount_cents = 99900

        result = await scorer.score(sample_event, features)

        assert result.score > 0.5
        assert result.triggered
        assert len(result.reasons) >= 3

    @pytest.mark.asyncio
    async def test_score_capped_at_one(self, scorer, sample_event):
        """Friendly fraud score should not exceed 1.0."""
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=10),
            entity=EntityFeatures(
                user_chargeback_count_90d=20,
                user_refund_count_90d=30,
                card_chargeback_count=5,
                device_chargeback_count=5,
                user_risk_tier="HIGH",
                user_is_guest=True,
            ),
            amount_cents=200000,
        )
        sample_event.amount_cents = 200000

        result = await scorer.score(sample_event, features)

        assert result.score <= 1.0


class TestSubscriptionAbuseScorer:
    """Tests for subscription abuse scoring."""

    @pytest_asyncio.fixture
    def scorer(self):
        return SubscriptionAbuseScorer()

    @pytest.mark.asyncio
    async def test_non_recurring_no_score(self, scorer, sample_event):
        """Non-recurring transactions should not trigger subscription abuse."""
        sample_event.is_recurring = False
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_is_new=True,
                card_is_new=True,
                ip_is_vpn=True,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score == 0.0
        assert not result.triggered
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_recurring_new_user_new_card_triggers(self, scorer, sample_event):
        """Recurring transaction from new user + new card should trigger."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=1),
            entity=EntityFeatures(
                user_is_new=True,
                card_is_new=True,
                ip_is_vpn=False,
                ip_is_proxy=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("SUBSCRIPTION_NEW_USER" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_recurring_high_velocity_triggers(self, scorer, sample_event):
        """Recurring transaction with high user velocity should trigger."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
                ip_is_vpn=False,
                ip_is_proxy=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("SUBSCRIPTION_HIGH_VELOCITY" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_recurring_vpn_triggers(self, scorer, sample_event):
        """Recurring transaction from VPN should trigger."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=1),
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
                ip_is_vpn=True,
                ip_is_proxy=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("SUBSCRIPTION_ANON_NETWORK" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_recurring_proxy_triggers(self, scorer, sample_event):
        """Recurring transaction from proxy should trigger."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=1),
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
                ip_is_vpn=False,
                ip_is_proxy=True,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0
        assert any("SUBSCRIPTION_ANON_NETWORK" in r.code for r in result.reasons)

    @pytest.mark.asyncio
    async def test_multiple_signals_compound(self, scorer, sample_event):
        """Multiple subscription abuse signals should compound."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_is_new=True,
                card_is_new=True,
                ip_is_vpn=True,
                ip_is_proxy=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score > 0.4
        assert result.triggered
        assert len(result.reasons) >= 2

    @pytest.mark.asyncio
    async def test_clean_recurring_no_score(self, scorer, sample_event):
        """Clean recurring transaction should not trigger."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=1),
            entity=EntityFeatures(
                user_is_new=False,
                card_is_new=False,
                ip_is_vpn=False,
                ip_is_proxy=False,
            ),
            amount_cents=2500,
        )

        result = await scorer.score(sample_event, features)

        assert result.score == 0.0
        assert not result.triggered


class TestSubscriptionAbuseIntegration:
    """Tests to verify SubscriptionAbuseScorer is integrated into RiskScorer."""

    @pytest_asyncio.fixture
    def scorer(self):
        return RiskScorer()

    @pytest.mark.asyncio
    async def test_subscription_abuse_propagates_to_friendly_fraud(self, scorer, sample_event):
        """Subscription abuse signals should propagate to friendly fraud score."""
        sample_event.is_recurring = True
        features = FeatureSet(
            velocity=VelocityFeatures(user_transactions_24h=5),
            entity=EntityFeatures(
                user_is_new=True,
                card_is_new=True,
                ip_is_vpn=True,
                card_total_transactions=0,
                user_total_transactions=0,
                device_total_transactions=0,
            ),
            amount_cents=2500,
        )

        scores, reasons = await scorer.compute_scores(sample_event, features)

        # Subscription abuse should increase friendly fraud score
        assert scores.friendly_fraud_score > 0
        # Should have subscription-related reason codes
        assert any("SUBSCRIPTION" in r.code for r in reasons)

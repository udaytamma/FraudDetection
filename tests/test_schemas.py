"""
Schema Tests

Tests for data validation and schema behavior.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from src.schemas import (
    PaymentEvent,
    DeviceInfo,
    GeoInfo,
    VerificationInfo,
    Decision,
    RiskScores,
    FraudDecisionResponse,
    VelocityFeatures,
    EntityFeatures,
    FeatureSet,
)


class TestPaymentEvent:
    """Tests for PaymentEvent schema."""

    def test_minimal_event(self):
        """Test creating event with minimal required fields."""
        event = PaymentEvent(
            transaction_id="txn_123",
            idempotency_key="idem_123",
            amount_cents=1000,
            card_token="card_abc",
            merchant_id="merchant_123",
        )

        assert event.transaction_id == "txn_123"
        assert event.amount_cents == 1000
        assert event.currency == "USD"  # default
        assert event.amount_dollars == 10.0

    def test_currency_uppercase(self):
        """Test that currency is normalized to uppercase."""
        event = PaymentEvent(
            transaction_id="txn_123",
            idempotency_key="idem_123",
            amount_cents=1000,
            card_token="card_abc",
            merchant_id="merchant_123",
            currency="usd",
        )

        assert event.currency == "USD"

    def test_high_value_threshold(self):
        """Test high value detection."""
        low_value = PaymentEvent(
            transaction_id="txn_1",
            idempotency_key="idem_1",
            amount_cents=50000,  # $500
            card_token="card_abc",
            merchant_id="merchant_123",
        )

        high_value = PaymentEvent(
            transaction_id="txn_2",
            idempotency_key="idem_2",
            amount_cents=150000,  # $1500
            card_token="card_abc",
            merchant_id="merchant_123",
        )

        assert not low_value.is_high_value
        assert high_value.is_high_value

    def test_3ds_detection(self):
        """Test 3DS detection."""
        no_3ds = PaymentEvent(
            transaction_id="txn_1",
            idempotency_key="idem_1",
            amount_cents=1000,
            card_token="card_abc",
            merchant_id="merchant_123",
        )

        with_3ds = PaymentEvent(
            transaction_id="txn_2",
            idempotency_key="idem_2",
            amount_cents=1000,
            card_token="card_abc",
            merchant_id="merchant_123",
            verification=VerificationInfo(
                three_ds_result="Y",
                three_ds_version="2.2",
            ),
        )

        assert not no_3ds.has_3ds
        assert with_3ds.has_3ds

    def test_invalid_bin(self):
        """Test that invalid BIN is rejected."""
        with pytest.raises(ValueError):
            PaymentEvent(
                transaction_id="txn_123",
                idempotency_key="idem_123",
                amount_cents=1000,
                card_token="card_abc",
                merchant_id="merchant_123",
                card_bin="abcdef",  # Invalid: not digits
            )

    def test_invalid_mcc(self):
        """Test that invalid MCC is rejected."""
        with pytest.raises(ValueError):
            PaymentEvent(
                transaction_id="txn_123",
                idempotency_key="idem_123",
                amount_cents=1000,
                card_token="card_abc",
                merchant_id="merchant_123",
                merchant_mcc="food",  # Invalid: not digits
            )


class TestRiskScores:
    """Tests for RiskScores schema."""

    def test_score_bounds(self):
        """Test that scores are bounded 0-1."""
        scores = RiskScores(
            risk_score=0.75,
            criminal_score=0.5,
            friendly_fraud_score=0.3,
        )

        assert 0 <= scores.risk_score <= 1
        assert 0 <= scores.criminal_score <= 1
        assert 0 <= scores.friendly_fraud_score <= 1

    def test_invalid_score_rejected(self):
        """Test that out-of-bound scores are rejected."""
        with pytest.raises(ValueError):
            RiskScores(
                risk_score=1.5,  # Invalid: > 1
                criminal_score=0.5,
            )


class TestVelocityFeatures:
    """Tests for VelocityFeatures schema."""

    def test_decline_rate_calculation(self):
        """Test decline rate calculation."""
        features = VelocityFeatures(
            card_attempts_10m=10,
            card_declines_10m=3,
        )

        assert features.card_decline_rate_10m == 0.3

    def test_decline_rate_zero_attempts(self):
        """Test decline rate with zero attempts."""
        features = VelocityFeatures(
            card_attempts_10m=0,
            card_declines_10m=0,
        )

        assert features.card_decline_rate_10m == 0.0


class TestDecision:
    """Tests for Decision enum."""

    def test_decision_values(self):
        """Test all decision values exist."""
        assert Decision.ALLOW.value == "ALLOW"
        assert Decision.FRICTION.value == "FRICTION"
        assert Decision.REVIEW.value == "REVIEW"
        assert Decision.BLOCK.value == "BLOCK"

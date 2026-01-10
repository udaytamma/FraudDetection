"""
Schema Tests - Telco/MSP Payment Fraud

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
    ServiceType,
    EventSubtype,
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
            service_id="mobile_prepaid_001",
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
            service_id="mobile_prepaid_001",
            currency="usd",
        )

        assert event.currency == "USD"

    def test_high_value_threshold(self):
        """Test high value detection (device upgrade, equipment purchase)."""
        low_value = PaymentEvent(
            transaction_id="txn_1",
            idempotency_key="idem_1",
            amount_cents=50000,  # $500
            card_token="card_abc",
            service_id="mobile_prepaid_001",
        )

        high_value = PaymentEvent(
            transaction_id="txn_2",
            idempotency_key="idem_2",
            amount_cents=150000,  # $1500 - device upgrade
            card_token="card_abc",
            service_id="mobile_prepaid_001",
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
            service_id="mobile_prepaid_001",
        )

        with_3ds = PaymentEvent(
            transaction_id="txn_2",
            idempotency_key="idem_2",
            amount_cents=1000,
            card_token="card_abc",
            service_id="mobile_prepaid_001",
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
                service_id="mobile_prepaid_001",
                card_bin="abcdef",  # Invalid: not digits
            )

    def test_telco_service_types(self):
        """Test telco service type and event subtype fields."""
        mobile_event = PaymentEvent(
            transaction_id="txn_123",
            idempotency_key="idem_123",
            amount_cents=2500,
            card_token="card_abc",
            service_id="mobile_prepaid_001",
            service_type=ServiceType.MOBILE,
            event_subtype=EventSubtype.SIM_ACTIVATION,
            phone_number="15551234567",
            imei="353456789012345",
        )

        assert mobile_event.service_type == ServiceType.MOBILE
        assert mobile_event.event_subtype == EventSubtype.SIM_ACTIVATION
        assert mobile_event.phone_number == "15551234567"

        broadband_event = PaymentEvent(
            transaction_id="txn_456",
            idempotency_key="idem_456",
            amount_cents=9900,
            card_token="card_xyz",
            service_id="broadband_fiber_001",
            service_type=ServiceType.BROADBAND,
            event_subtype=EventSubtype.SERVICE_ACTIVATION,
            modem_mac="00:1A:2B:3C:4D:5E",
        )

        assert broadband_event.service_type == ServiceType.BROADBAND
        assert broadband_event.event_subtype == EventSubtype.SERVICE_ACTIVATION

    def test_high_risk_subtype(self):
        """Test high-risk event subtype detection."""
        # Device upgrade is high risk (resale fraud)
        device_upgrade = PaymentEvent(
            transaction_id="txn_1",
            idempotency_key="idem_1",
            amount_cents=99900,
            card_token="card_abc",
            service_id="mobile_001",
            event_subtype=EventSubtype.DEVICE_UPGRADE,
        )
        assert device_upgrade.is_high_risk_subtype

        # SIM swap is high risk (account takeover)
        sim_swap = PaymentEvent(
            transaction_id="txn_2",
            idempotency_key="idem_2",
            amount_cents=0,
            card_token="card_abc",
            service_id="mobile_001",
            event_subtype=EventSubtype.SIM_SWAP,
        )
        assert sim_swap.is_high_risk_subtype

        # Topup is not high risk
        topup = PaymentEvent(
            transaction_id="txn_3",
            idempotency_key="idem_3",
            amount_cents=2000,
            card_token="card_abc",
            service_id="mobile_001",
            event_subtype=EventSubtype.TOPUP,
        )
        assert not topup.is_high_risk_subtype


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

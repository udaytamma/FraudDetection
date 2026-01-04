"""
Decision Schemas

Defines the decision types and response structures for the
fraud detection API. Decisions follow a hierarchy:
ALLOW < FRICTION < REVIEW < BLOCK
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class Decision(str, Enum):
    """
    Fraud decision outcomes.

    Ordered by severity (ALLOW is least severe, BLOCK is most severe):
    - ALLOW: Proceed with transaction (revenue captured, fraud risk accepted)
    - FRICTION: Request additional verification (3DS, OTP, step-up auth)
    - REVIEW: Hold for manual analyst review (delay, higher accuracy)
    - BLOCK: Decline transaction (zero fraud risk, potential lost revenue)
    """
    ALLOW = "ALLOW"
    FRICTION = "FRICTION"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class DecisionReason(BaseModel):
    """
    Reason for a fraud decision.

    Provides transparency into why a decision was made.
    Used for:
    - Analyst review context
    - Evidence for disputes
    - Model explainability
    - Debugging and monitoring
    """
    code: str = Field(
        ...,
        description="Machine-readable reason code (e.g., 'VELOCITY_CARD_1H')",
    )
    description: str = Field(
        ...,
        description="Human-readable description",
    )
    severity: str = Field(
        default="MEDIUM",
        description="Severity level: LOW, MEDIUM, HIGH, CRITICAL",
    )
    triggered_by: Optional[str] = Field(
        default=None,
        description="Which detector triggered this reason",
    )
    value: Optional[str] = Field(
        default=None,
        description="Actual value that triggered the rule (for debugging)",
    )
    threshold: Optional[str] = Field(
        default=None,
        description="Threshold that was exceeded",
    )


class RiskScores(BaseModel):
    """
    Risk scores computed by the scoring engine.

    Separate scores for different fraud types allow
    for tailored policy responses.
    """
    # Overall risk score (0.0 to 1.0)
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall fraud risk score",
    )

    # Component scores
    criminal_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Criminal fraud risk score (stolen cards, bots, fraud rings)",
    )
    friendly_fraud_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Friendly fraud risk score (abuse, disputes, refund gaming)",
    )

    # Confidence (how much data we have)
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in the score (based on data availability)",
    )

    # Individual detector signals (for debugging and explainability)
    card_testing_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Card testing detection score",
    )
    velocity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Velocity attack detection score",
    )
    geo_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Geographic anomaly score",
    )
    bot_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Bot/automation detection score",
    )


class FraudDecisionResponse(BaseModel):
    """
    Complete fraud decision response.

    Returned by the /decide endpoint with full context for:
    - Transaction processing (decision)
    - Evidence capture (all fields)
    - Monitoring and debugging (scores, reasons, latency)
    """
    # Transaction identifiers
    transaction_id: str = Field(
        ...,
        description="Transaction ID from the request",
    )
    idempotency_key: str = Field(
        ...,
        description="Idempotency key from the request",
    )

    # Decision
    decision: Decision = Field(
        ...,
        description="Fraud decision",
    )
    reasons: list[DecisionReason] = Field(
        default_factory=list,
        description="Reasons for the decision",
    )

    # Scores
    scores: RiskScores = Field(
        ...,
        description="Risk scores",
    )

    # Friction instructions (if decision is FRICTION)
    friction_type: Optional[str] = Field(
        default=None,
        description="Type of friction to apply: 3DS, OTP, STEP_UP",
    )
    friction_message: Optional[str] = Field(
        default=None,
        description="Message to display for friction",
    )

    # Review instructions (if decision is REVIEW)
    review_priority: Optional[str] = Field(
        default=None,
        description="Review priority: LOW, MEDIUM, HIGH, URGENT",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="Notes for analyst",
    )

    # Timing information
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="When decision was made",
    )
    processing_time_ms: float = Field(
        default=0.0,
        description="Total processing time in milliseconds",
    )

    # Component latencies (for SLA monitoring)
    feature_time_ms: float = Field(
        default=0.0,
        description="Feature computation time in milliseconds",
    )
    scoring_time_ms: float = Field(
        default=0.0,
        description="Scoring time in milliseconds",
    )
    policy_time_ms: float = Field(
        default=0.0,
        description="Policy evaluation time in milliseconds",
    )

    # Metadata
    policy_version: str = Field(
        default="1.0.0",
        description="Policy version used for this decision",
    )
    is_cached: bool = Field(
        default=False,
        description="Whether result was from idempotency cache",
    )


# =============================================================================
# Reason Codes (Constants)
# =============================================================================

class ReasonCodes:
    """
    Standard reason codes for fraud decisions.

    Format: {CATEGORY}_{SUBCATEGORY}_{DETAIL}
    """
    # Card Testing
    CARD_TESTING_VELOCITY = "CARD_TESTING_VELOCITY"
    CARD_TESTING_DECLINE_RATIO = "CARD_TESTING_DECLINE_RATIO"
    CARD_TESTING_SMALL_AMOUNTS = "CARD_TESTING_SMALL_AMOUNTS"

    # Velocity Attacks
    VELOCITY_CARD_10M = "VELOCITY_CARD_10M"
    VELOCITY_CARD_1H = "VELOCITY_CARD_1H"
    VELOCITY_DEVICE_CARDS = "VELOCITY_DEVICE_CARDS"
    VELOCITY_IP_CARDS = "VELOCITY_IP_CARDS"
    VELOCITY_USER_24H = "VELOCITY_USER_24H"

    # Geographic
    GEO_IMPOSSIBLE_TRAVEL = "GEO_IMPOSSIBLE_TRAVEL"
    GEO_COUNTRY_MISMATCH = "GEO_COUNTRY_MISMATCH"
    GEO_HIGH_RISK_COUNTRY = "GEO_HIGH_RISK_COUNTRY"

    # Bot/Automation
    BOT_EMULATOR = "BOT_EMULATOR"
    BOT_ROOTED_DEVICE = "BOT_ROOTED_DEVICE"
    BOT_DATACENTER_IP = "BOT_DATACENTER_IP"
    BOT_TOR_EXIT = "BOT_TOR_EXIT"
    BOT_VPN_PROXY = "BOT_VPN_PROXY"

    # Friendly Fraud
    FRIENDLY_HIGH_CHARGEBACK_RATE = "FRIENDLY_HIGH_CHARGEBACK_RATE"
    FRIENDLY_HIGH_REFUND_RATE = "FRIENDLY_HIGH_REFUND_RATE"
    FRIENDLY_DISPUTE_HISTORY = "FRIENDLY_DISPUTE_HISTORY"

    # High Value
    HIGH_VALUE_NEW_ACCOUNT = "HIGH_VALUE_NEW_ACCOUNT"
    HIGH_VALUE_NEW_CARD = "HIGH_VALUE_NEW_CARD"
    HIGH_VALUE_RISK_SCORE = "HIGH_VALUE_RISK_SCORE"

    # Verification
    VERIFICATION_AVS_MISMATCH = "VERIFICATION_AVS_MISMATCH"
    VERIFICATION_CVV_MISMATCH = "VERIFICATION_CVV_MISMATCH"
    VERIFICATION_NO_3DS = "VERIFICATION_NO_3DS"

    # Blocklist
    BLOCKLIST_CARD = "BLOCKLIST_CARD"
    BLOCKLIST_DEVICE = "BLOCKLIST_DEVICE"
    BLOCKLIST_IP = "BLOCKLIST_IP"
    BLOCKLIST_USER = "BLOCKLIST_USER"

    # Allowlist
    ALLOWLIST_CARD = "ALLOWLIST_CARD"
    ALLOWLIST_USER = "ALLOWLIST_USER"
    ALLOWLIST_MERCHANT = "ALLOWLIST_MERCHANT"

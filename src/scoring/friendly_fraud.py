"""
Friendly Fraud Scoring - Telco/MSP Payment Fraud

Scores risk of friendly fraud (first-party abuse):
1. Subscriber disputes legitimate service charges
2. Service cancellation after device receipt (device upgrade fraud)
3. Subscription abuse (sign up, use, chargeback)
4. "Buyer's remorse" chargebacks after equipment purchase

Telco-specific patterns:
- Device upgrade, receive phone, then chargeback
- Equipment purchase with subsequent dispute
- Service activation followed by immediate cancellation
- International roaming usage then dispute

Key signals:
- Historical chargeback rate
- Refund patterns
- Dispute history
- Account behavior consistency
"""

from ..schemas import PaymentEvent, FeatureSet, DecisionReason, ReasonCodes
from ..detection.detector import DetectionResult


class FriendlyFraudScorer:
    """
    Scores friendly fraud risk.

    Friendly fraud requires different treatment than criminal fraud:
    - Often from legitimate subscribers
    - Response is friction/limits rather than blocks
    - Evidence is critical for representment

    In telco context, common patterns include:
    - Device upgrade fraud: receive subsidized device, then dispute
    - Equipment fraud: receive CPE/modem, then chargeback
    - Service abuse: use service (roaming, data), then dispute
    """

    def __init__(
        self,
        chargeback_rate_threshold: float = 0.03,  # 3%
        high_chargeback_count_threshold: int = 2,
        high_refund_count_threshold: int = 5,
    ):
        """
        Initialize scorer.

        Args:
            chargeback_rate_threshold: Rate to flag as high-risk
            high_chargeback_count_threshold: Count to flag (absolute)
            high_refund_count_threshold: Refund count to flag
        """
        self.chargeback_rate_threshold = chargeback_rate_threshold
        self.high_chargeback_count = high_chargeback_count_threshold
        self.high_refund_count = high_refund_count_threshold

    async def score(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Score friendly fraud risk.

        Args:
            event: Payment event
            features: Feature set

        Returns:
            DetectionResult with friendly fraud score
        """
        result = DetectionResult()
        signals = []

        # =======================================================================
        # Check 1: Historical chargeback rate (user)
        # =======================================================================
        user_chargebacks_90d = features.entity.user_chargeback_count_90d
        user_txns_30d = features.velocity.user_transactions_24h * 30  # Rough estimate

        if user_txns_30d > 0:
            estimated_rate = user_chargebacks_90d / max(user_txns_30d, 1)
            if estimated_rate >= self.chargeback_rate_threshold:
                signals.append(0.7)
                result.add_reason(
                    code=ReasonCodes.FRIENDLY_HIGH_CHARGEBACK_RATE,
                    description=f"User has {estimated_rate:.1%} chargeback rate in 90 days",
                    severity="HIGH",
                    value=f"{estimated_rate:.2%}",
                    threshold=f"{self.chargeback_rate_threshold:.0%}",
                )

        # =======================================================================
        # Check 2: Absolute chargeback count (user)
        # =======================================================================
        if user_chargebacks_90d >= self.high_chargeback_count:
            signals.append(0.6)
            result.add_reason(
                code=ReasonCodes.FRIENDLY_DISPUTE_HISTORY,
                description=f"User has {user_chargebacks_90d} chargebacks in 90 days",
                severity="HIGH",
                value=str(user_chargebacks_90d),
                threshold=str(self.high_chargeback_count),
            )

        # =======================================================================
        # Check 3: High refund count (potential gaming)
        # =======================================================================
        refund_count = features.entity.user_refund_count_90d

        if refund_count >= self.high_refund_count:
            # Refunds alone are less concerning than chargebacks
            signals.append(0.4)
            result.add_reason(
                code=ReasonCodes.FRIENDLY_HIGH_REFUND_RATE,
                description=f"User has {refund_count} refunds in 90 days",
                severity="MEDIUM",
                value=str(refund_count),
                threshold=str(self.high_refund_count),
            )

        # =======================================================================
        # Check 4: Card-level chargeback history
        # =======================================================================
        card_chargebacks = features.entity.card_chargeback_count

        if card_chargebacks >= 1:
            signals.append(0.5)
            result.add_reason(
                code="CARD_CHARGEBACK_HISTORY",
                description=f"Card has {card_chargebacks} prior chargebacks",
                severity="MEDIUM",
                value=str(card_chargebacks),
            )

        # =======================================================================
        # Check 5: Device-level chargeback history
        # =======================================================================
        device_chargebacks = features.entity.device_chargeback_count

        if device_chargebacks >= 2:
            signals.append(0.5)
            result.add_reason(
                code="DEVICE_CHARGEBACK_HISTORY",
                description=f"Device has {device_chargebacks} prior chargebacks",
                severity="MEDIUM",
                value=str(device_chargebacks),
            )

        # =======================================================================
        # Check 6: Risk tier escalation
        # =======================================================================
        risk_tier = features.entity.user_risk_tier

        if risk_tier == "HIGH":
            signals.append(0.6)
            result.add_reason(
                code="USER_HIGH_RISK_TIER",
                description="User is classified as high-risk",
                severity="HIGH",
            )
        elif risk_tier == "ELEVATED":
            signals.append(0.4)
            result.add_reason(
                code="USER_ELEVATED_RISK_TIER",
                description="User is classified as elevated-risk",
                severity="MEDIUM",
            )

        # =======================================================================
        # Check 7: Guest/new subscriber for high value (device upgrade, equipment)
        # Telco context: New subscriber getting subsidized device is high risk
        # =======================================================================
        if features.entity.user_is_guest and event.amount_cents >= 50000:  # $500
            # Guest/new subscriber for high value is higher risk for friendly fraud
            # In telco: device upgrades, equipment purchases from new accounts
            signals.append(0.4)
            result.add_reason(
                code="GUEST_HIGH_VALUE",
                description=f"Guest/new subscriber for ${event.amount_cents/100:.2f}",
                severity="MEDIUM",
                value=f"${event.amount_cents/100:.2f}",
            )

        # =======================================================================
        # Compute final score
        # =======================================================================
        if signals:
            result.score = min(1.0, max(signals) + 0.03 * (len(signals) - 1))
            result.triggered = result.score >= 0.3

        return result


class SubscriptionAbuseScorer:
    """
    Scores risk of subscription abuse.

    Patterns:
    - Sign up, use service, chargeback
    - Multiple free trials / promotional abuse
    - Payment method cycling

    Telco-specific patterns:
    - Multiple new line promotions from same household
    - Service activation with immediate high usage then dispute
    - International roaming enable, use, then chargeback
    """

    async def score(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Score subscription abuse risk.

        Minimal heuristics using available features (capstone scope).
        """
        result = DetectionResult()
        signals = []

        # Only applies to recurring transactions
        if not event.is_recurring:
            return result

        # Signal 1: New user + new card on recurring charge
        if features.entity.user_is_new and features.entity.card_is_new:
            signals.append(0.4)
            result.add_reason(
                code=ReasonCodes.SUBSCRIPTION_NEW_USER,
                description="New user and new card on recurring charge",
                severity="MEDIUM",
            )

        # Signal 2: High short-term velocity for user
        if features.velocity.user_transactions_24h >= 3:
            signals.append(0.3)
            result.add_reason(
                code=ReasonCodes.SUBSCRIPTION_HIGH_VELOCITY,
                description="High 24h user velocity on recurring charge",
                severity="LOW",
                value=str(features.velocity.user_transactions_24h),
            )

        # Signal 3: Network anonymity
        if features.entity.ip_is_vpn or features.entity.ip_is_proxy:
            signals.append(0.2)
            result.add_reason(
                code=ReasonCodes.SUBSCRIPTION_ANON_NETWORK,
                description="Recurring charge from VPN/proxy network",
                severity="LOW",
            )

        if signals:
            result.score = min(1.0, max(signals) + 0.05 * (len(signals) - 1))
            result.triggered = result.score >= 0.3

        return result

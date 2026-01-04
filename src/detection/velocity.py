"""
Velocity Attack Detection

Detects abnormal transaction velocity patterns that indicate:
1. Stolen card being used rapidly before block
2. Account takeover with rapid purchases
3. Fraud rings hitting a merchant
4. Automated fraud using bots

Key signals:
- Transaction count exceeds normal patterns
- Amount velocity exceeds limits
- Distinct entity counts (cards per device, merchants per card)
"""

from ..config import settings
from ..schemas import PaymentEvent, FeatureSet, DecisionReason, ReasonCodes
from .detector import BaseDetector, DetectionResult


class VelocityAttackDetector(BaseDetector):
    """
    Detects abnormal transaction velocity.

    Velocity attacks are characterized by:
    - High transaction frequency from single entity
    - Unusual patterns (many merchants, many cards, etc.)
    - Amount accumulation exceeding normal limits
    """

    def __init__(
        self,
        card_attempts_1h_threshold: int = None,
        device_cards_24h_threshold: int = None,
        ip_cards_1h_threshold: int = None,
        user_amount_24h_threshold_cents: int = 500000,  # $5000
    ):
        """
        Initialize detector.

        Args:
            card_attempts_1h_threshold: Max card attempts per hour
            device_cards_24h_threshold: Max cards per device per day
            ip_cards_1h_threshold: Max cards per IP per hour
            user_amount_24h_threshold_cents: Max user spend per day
        """
        self.card_attempts_1h = card_attempts_1h_threshold or settings.velocity_card_attempts_1h_threshold
        self.device_cards_24h = device_cards_24h_threshold or settings.velocity_device_cards_24h_threshold
        self.ip_cards_1h = ip_cards_1h_threshold or settings.velocity_ip_cards_1h_threshold
        self.user_amount_24h = user_amount_24h_threshold_cents

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Run velocity attack detection.

        Checks multiple velocity dimensions:
        - Card velocity (attempts per time window)
        - Device velocity (cards per device)
        - IP velocity (cards per IP)
        - User velocity (transactions and amount)
        """
        result = DetectionResult()
        signals = []

        # =======================================================================
        # Check 1: Card velocity (1-hour window)
        # =======================================================================
        card_attempts = features.velocity.card_attempts_1h

        if card_attempts >= self.card_attempts_1h:
            severity = "CRITICAL" if card_attempts >= self.card_attempts_1h * 2 else "HIGH"
            score = min(1.0, card_attempts / (self.card_attempts_1h * 2))
            signals.append(score)

            result.add_reason(
                code=ReasonCodes.VELOCITY_CARD_1H,
                description=f"Card has {card_attempts} transactions in 1 hour",
                severity=severity,
                value=str(card_attempts),
                threshold=str(self.card_attempts_1h),
            )

        # =======================================================================
        # Check 2: Device-to-card velocity
        # =======================================================================
        device_cards = features.velocity.device_distinct_cards_24h

        if device_cards >= self.device_cards_24h:
            severity = "CRITICAL" if device_cards >= self.device_cards_24h * 2 else "HIGH"
            score = min(1.0, device_cards / (self.device_cards_24h * 2))
            signals.append(score)

            result.add_reason(
                code=ReasonCodes.VELOCITY_DEVICE_CARDS,
                description=f"Device used {device_cards} different cards in 24 hours",
                severity=severity,
                value=str(device_cards),
                threshold=str(self.device_cards_24h),
            )

        # =======================================================================
        # Check 3: IP-to-card velocity
        # =======================================================================
        ip_cards = features.velocity.ip_distinct_cards_1h

        if ip_cards >= self.ip_cards_1h:
            severity = "HIGH"
            score = min(1.0, ip_cards / (self.ip_cards_1h * 2))
            signals.append(score)

            result.add_reason(
                code=ReasonCodes.VELOCITY_IP_CARDS,
                description=f"IP used {ip_cards} different cards in 1 hour",
                severity=severity,
                value=str(ip_cards),
                threshold=str(self.ip_cards_1h),
            )

        # =======================================================================
        # Check 4: User velocity (transactions)
        # =======================================================================
        user_txns = features.velocity.user_transactions_24h

        if user_txns >= 20:  # More than 20 transactions per day is unusual
            score = min(1.0, user_txns / 40)
            signals.append(score * 0.5)  # Weight lower as high txn users exist

            result.add_reason(
                code=ReasonCodes.VELOCITY_USER_24H,
                description=f"User has {user_txns} transactions in 24 hours",
                severity="MEDIUM",
                value=str(user_txns),
                threshold="20",
            )

        # =======================================================================
        # Check 5: User velocity (amount)
        # =======================================================================
        user_amount = features.velocity.user_amount_24h_cents

        if user_amount >= self.user_amount_24h:
            score = min(1.0, user_amount / (self.user_amount_24h * 2))
            signals.append(score * 0.6)  # Amount limits are softer

            result.add_reason(
                code="VELOCITY_USER_AMOUNT_24H",
                description=f"User spent ${user_amount/100:.2f} in 24 hours",
                severity="MEDIUM",
                value=f"${user_amount/100:.2f}",
                threshold=f"${self.user_amount_24h/100:.2f}",
            )

        # =======================================================================
        # Check 6: Card spreading across many merchants
        # =======================================================================
        card_merchants = features.velocity.card_distinct_merchants_24h

        if card_merchants >= 10:
            score = min(1.0, card_merchants / 20)
            signals.append(score * 0.5)

            result.add_reason(
                code="VELOCITY_CARD_MERCHANTS",
                description=f"Card used at {card_merchants} merchants in 24 hours",
                severity="MEDIUM",
                value=str(card_merchants),
                threshold="10",
            )

        # =======================================================================
        # Check 7: Card spreading across many devices/IPs
        # =======================================================================
        card_devices = features.velocity.card_distinct_devices_24h
        card_ips = features.velocity.card_distinct_ips_24h

        if card_devices >= 3 or card_ips >= 5:
            score = min(1.0, max(card_devices / 6, card_ips / 10))
            signals.append(score * 0.6)

            if card_devices >= 3:
                result.add_reason(
                    code="VELOCITY_CARD_DEVICES",
                    description=f"Card used from {card_devices} devices in 24 hours",
                    severity="MEDIUM",
                    value=str(card_devices),
                    threshold="3",
                )

            if card_ips >= 5:
                result.add_reason(
                    code="VELOCITY_CARD_IPS",
                    description=f"Card used from {card_ips} IPs in 24 hours",
                    severity="MEDIUM",
                    value=str(card_ips),
                    threshold="5",
                )

        # =======================================================================
        # Compute final score
        # =======================================================================
        if signals:
            # Use max signal with boost for multiple signals
            result.score = min(1.0, max(signals) + 0.03 * (len(signals) - 1))
            result.triggered = result.score >= 0.4

        return result

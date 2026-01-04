"""
Card Testing Detection

Detects card testing/enumeration attacks where fraudsters:
1. Test stolen cards with small transactions
2. Probe multiple cards rapidly to find working ones
3. Use sequential or patterned card numbers (BIN attacks)

Key signals:
- High velocity of attempts on same card
- High decline rate on card
- Small transaction amounts ($1-5)
- Multiple cards from same device/IP in short time
"""

from ..config import settings
from ..schemas import PaymentEvent, FeatureSet, DecisionReason, ReasonCodes
from .detector import BaseDetector, DetectionResult


class CardTestingDetector(BaseDetector):
    """
    Detects card testing and BIN enumeration attacks.

    Card testing is characterized by:
    - Rapid succession of small transactions
    - High decline rate as fraudsters probe for valid cards
    - Often from single device/IP hitting many cards
    """

    def __init__(
        self,
        velocity_threshold_10m: int = None,
        decline_ratio_threshold: float = None,
        small_amount_threshold_cents: int = 500,  # $5
    ):
        """
        Initialize detector.

        Args:
            velocity_threshold_10m: Max attempts in 10 min (default from settings)
            decline_ratio_threshold: Decline ratio to trigger (default from settings)
            small_amount_threshold_cents: Amount below which is "small"
        """
        self.velocity_threshold = velocity_threshold_10m or settings.card_testing_attempts_threshold
        self.decline_ratio_threshold = decline_ratio_threshold or settings.card_testing_decline_ratio_threshold
        self.small_amount_threshold = small_amount_threshold_cents

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Run card testing detection.

        Checks:
        1. Card velocity exceeds threshold
        2. High decline ratio on card
        3. Small transaction amount + velocity pattern
        4. Multiple cards from same device (BIN attack signal)
        """
        result = DetectionResult()
        signals = []  # Collect signals to compute final score

        # =======================================================================
        # Check 1: Card velocity in 10-minute window
        # =======================================================================
        card_attempts = features.velocity.card_attempts_10m

        if card_attempts >= self.velocity_threshold:
            signals.append(0.8)
            result.add_reason(
                code=ReasonCodes.CARD_TESTING_VELOCITY,
                description=f"Card has {card_attempts} attempts in 10 minutes",
                severity="HIGH",
                value=str(card_attempts),
                threshold=str(self.velocity_threshold),
            )

        # =======================================================================
        # Check 2: High decline ratio
        # =======================================================================
        decline_rate = features.velocity.card_decline_rate_10m

        if decline_rate >= self.decline_ratio_threshold and card_attempts >= 3:
            signals.append(0.9)
            result.add_reason(
                code=ReasonCodes.CARD_TESTING_DECLINE_RATIO,
                description=f"Card has {decline_rate:.0%} decline rate in 10 minutes",
                severity="HIGH",
                value=f"{decline_rate:.2%}",
                threshold=f"{self.decline_ratio_threshold:.0%}",
            )

        # =======================================================================
        # Check 3: Small amount + velocity pattern
        # =======================================================================
        is_small_amount = event.amount_cents <= self.small_amount_threshold

        if is_small_amount and card_attempts >= 2:
            # Small amounts with velocity = likely testing
            signals.append(0.6)
            result.add_reason(
                code=ReasonCodes.CARD_TESTING_SMALL_AMOUNTS,
                description=f"Small amount (${event.amount_cents/100:.2f}) with prior attempts",
                severity="MEDIUM",
                value=f"${event.amount_cents/100:.2f}",
                threshold=f"${self.small_amount_threshold/100:.2f}",
            )

        # =======================================================================
        # Check 4: Device/IP hitting many cards (BIN attack)
        # =======================================================================
        device_cards = features.velocity.device_distinct_cards_1h
        ip_cards = features.velocity.ip_distinct_cards_1h

        if device_cards >= 5:
            signals.append(0.85)
            result.add_reason(
                code=ReasonCodes.VELOCITY_DEVICE_CARDS,
                description=f"Device used {device_cards} different cards in 1 hour",
                severity="HIGH",
                value=str(device_cards),
                threshold="5",
            )

        if ip_cards >= 10:
            signals.append(0.8)
            result.add_reason(
                code=ReasonCodes.VELOCITY_IP_CARDS,
                description=f"IP used {ip_cards} different cards in 1 hour",
                severity="HIGH",
                value=str(ip_cards),
                threshold="10",
            )

        # =======================================================================
        # Compute final score
        # =======================================================================
        if signals:
            # Use max signal with slight boost for multiple signals
            result.score = min(1.0, max(signals) + 0.05 * (len(signals) - 1))
            result.triggered = result.score >= 0.5

        return result


class BINAttackDetector(BaseDetector):
    """
    Specialized detector for BIN enumeration attacks.

    BIN attacks involve:
    - Sequential card numbers being tested
    - Same BIN (first 6 digits) across many attempts
    - Typically from single device/IP
    """

    def __init__(
        self,
        same_bin_threshold: int = 10,
        sequential_detection: bool = True,
    ):
        """
        Initialize BIN attack detector.

        Args:
            same_bin_threshold: Cards with same BIN to trigger
            sequential_detection: Check for sequential patterns
        """
        self.same_bin_threshold = same_bin_threshold
        self.sequential_detection = sequential_detection

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Detect BIN enumeration attacks.

        Note: Full BIN tracking requires additional Redis structures
        to track BIN distribution per device/IP. This is a simplified
        version that relies on existing velocity features.
        """
        result = DetectionResult()

        # High card diversity from single source is primary signal
        device_cards = features.velocity.device_distinct_cards_1h
        ip_cards = features.velocity.ip_distinct_cards_1h

        # Combined signal: many distinct cards from device + IP
        if device_cards >= 3 and ip_cards >= 5:
            # Likely coordinated attack
            score = min(1.0, (device_cards / 5) * 0.3 + (ip_cards / 10) * 0.4)
            result.score = score
            result.triggered = score >= 0.5

            if result.triggered:
                result.add_reason(
                    code="BIN_ATTACK_SUSPECTED",
                    description=f"Multiple cards ({device_cards} device, {ip_cards} IP) suggest BIN attack",
                    severity="HIGH",
                    value=f"device:{device_cards}, ip:{ip_cards}",
                )

        return result

"""
Risk Scoring Engine

Combines signals from all detection modules into final risk scores.
This is a rule-based scorer for Phase 1 (ML deferred to Phase 2).

Produces:
- Overall risk score (0.0 to 1.0)
- Criminal fraud score
- Friendly fraud score
- Confidence level
"""

from ..schemas import (
    PaymentEvent,
    FeatureSet,
    RiskScores,
    DecisionReason,
)
from ..detection import (
    DetectionEngine,
    CardTestingDetector,
    VelocityAttackDetector,
    GeoAnomalyDetector,
    BotDetector,
)
from .friendly_fraud import FriendlyFraudScorer


class RiskScorer:
    """
    Main risk scoring engine.

    Orchestrates all detection modules and combines results
    into a unified risk assessment.
    """

    def __init__(self):
        """Initialize risk scorer with all detectors."""
        # Initialize individual detectors
        self.card_testing = CardTestingDetector()
        self.velocity = VelocityAttackDetector()
        self.geo = GeoAnomalyDetector()
        self.bot = BotDetector()
        self.friendly_fraud = FriendlyFraudScorer()

        # Detection engine orchestrates the detectors
        self.detection_engine = DetectionEngine([
            self.card_testing,
            self.velocity,
            self.geo,
            self.bot,
        ])

    async def compute_scores(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> tuple[RiskScores, list[DecisionReason]]:
        """
        Compute all risk scores for a transaction.

        Args:
            event: Payment event
            features: Computed feature set

        Returns:
            Tuple of (RiskScores, list of triggered reasons)
        """
        # Run all criminal fraud detectors in parallel
        detector_results, reasons = await self.detection_engine.run_detection(
            event, features
        )

        # Run friendly fraud scorer
        friendly_result = await self.friendly_fraud.score(event, features)
        reasons.extend(friendly_result.reasons)

        # Extract individual scores
        card_testing_score = detector_results.get("CardTestingDetector", type("", (), {"score": 0.0})()).score
        velocity_score = detector_results.get("VelocityAttackDetector", type("", (), {"score": 0.0})()).score
        geo_score = detector_results.get("GeoAnomalyDetector", type("", (), {"score": 0.0})()).score
        bot_score = detector_results.get("BotDetector", type("", (), {"score": 0.0})()).score

        # Compute aggregate criminal score
        # Use weighted max - certain signals are more indicative
        criminal_scores = [
            (card_testing_score, 1.0),   # Full weight
            (velocity_score, 0.9),        # Slightly lower
            (geo_score, 0.7),             # Geo can have false positives
            (bot_score, 1.0),             # Bot signals are strong
        ]

        weighted_max = max(score * weight for score, weight in criminal_scores)
        criminal_score = min(1.0, weighted_max)

        # Friendly fraud score from dedicated scorer
        friendly_score = friendly_result.score

        # Overall risk score - max of criminal and friendly
        # with adjustment for confidence
        confidence = self._compute_confidence(event, features)
        risk_score = max(criminal_score, friendly_score)

        # Adjust risk score based on confidence
        # Low confidence = less extreme scores
        if confidence < 0.5:
            risk_score = 0.3 + (risk_score - 0.3) * confidence * 2

        return RiskScores(
            risk_score=round(risk_score, 4),
            criminal_score=round(criminal_score, 4),
            friendly_fraud_score=round(friendly_score, 4),
            confidence=round(confidence, 4),
            card_testing_score=round(card_testing_score, 4),
            velocity_score=round(velocity_score, 4),
            geo_score=round(geo_score, 4),
            bot_score=round(bot_score, 4),
        ), reasons

    def _compute_confidence(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> float:
        """
        Compute confidence level based on data availability.

        Higher confidence when we have more history on entities.

        Args:
            event: Payment event
            features: Feature set

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence_factors = []

        # Card history
        if not features.entity.card_is_new:
            card_txns = features.entity.card_total_transactions
            confidence_factors.append(min(1.0, card_txns / 10))
        else:
            confidence_factors.append(0.3)  # New card = low confidence

        # User history
        if not features.entity.user_is_guest and not features.entity.user_is_new:
            user_txns = features.entity.user_total_transactions
            confidence_factors.append(min(1.0, user_txns / 20))
        else:
            confidence_factors.append(0.3)  # New/guest user = low confidence

        # Device history
        device_txns = features.entity.device_total_transactions
        if device_txns > 0:
            confidence_factors.append(min(1.0, device_txns / 5))
        else:
            confidence_factors.append(0.4)

        # Data completeness
        has_device = event.device is not None
        has_geo = event.geo is not None
        has_verification = event.verification is not None

        completeness = (
            (0.3 if has_device else 0) +
            (0.3 if has_geo else 0) +
            (0.4 if has_verification else 0)
        )
        confidence_factors.append(completeness)

        # Average confidence factors
        return sum(confidence_factors) / len(confidence_factors)


class HighValueTransactionScorer:
    """
    Additional scoring for high-value transactions.

    High-value transactions get extra scrutiny.
    """

    def __init__(
        self,
        high_value_threshold_cents: int = 100000,  # $1000
        new_account_days: int = 7,
    ):
        """
        Initialize scorer.

        Args:
            high_value_threshold_cents: Amount threshold
            new_account_days: Days for "new account"
        """
        self.threshold = high_value_threshold_cents
        self.new_account_days = new_account_days

    def score(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> tuple[float, list[DecisionReason]]:
        """
        Score high-value transaction risk.

        Args:
            event: Payment event
            features: Feature set

        Returns:
            Tuple of (score, reasons)
        """
        reasons = []
        signals = []

        if event.amount_cents < self.threshold:
            return 0.0, reasons

        # High value from new account
        if features.entity.user_is_new or features.entity.user_is_guest:
            signals.append(0.6)
            reasons.append(DecisionReason(
                code="HIGH_VALUE_NEW_ACCOUNT",
                description=f"High-value (${event.amount_cents/100:.2f}) from new account",
                severity="HIGH",
                value=f"${event.amount_cents/100:.2f}",
            ))

        # High value with new card
        if features.entity.card_is_new:
            signals.append(0.5)
            reasons.append(DecisionReason(
                code="HIGH_VALUE_NEW_CARD",
                description=f"High-value (${event.amount_cents/100:.2f}) with first-seen card",
                severity="MEDIUM",
                value=f"${event.amount_cents/100:.2f}",
            ))

        # High value without 3DS
        if not features.has_3ds:
            signals.append(0.4)
            reasons.append(DecisionReason(
                code="HIGH_VALUE_NO_3DS",
                description=f"High-value (${event.amount_cents/100:.2f}) without 3DS",
                severity="MEDIUM",
            ))

        # High value with verification failures
        if not features.avs_match:
            signals.append(0.5)
            reasons.append(DecisionReason(
                code="HIGH_VALUE_AVS_FAIL",
                description="High-value transaction with AVS mismatch",
                severity="HIGH",
            ))

        if not features.cvv_match:
            signals.append(0.6)
            reasons.append(DecisionReason(
                code="HIGH_VALUE_CVV_FAIL",
                description="High-value transaction with CVV mismatch",
                severity="HIGH",
            ))

        if signals:
            score = min(1.0, max(signals) + 0.05 * (len(signals) - 1))
            return score, reasons

        return 0.0, reasons

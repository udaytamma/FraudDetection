"""
Friendly Fraud Detector

Wraps friendly-fraud and subscription-abuse scoring into a detector
so it can run inside the detection engine alongside criminal detectors.
"""

from .detector import BaseDetector, DetectionResult
from ..schemas import PaymentEvent, FeatureSet
from ..scoring.friendly_fraud import FriendlyFraudScorer, SubscriptionAbuseScorer


class FriendlyFraudDetector(BaseDetector):
    """Detector for first-party abuse and subscription abuse signals."""

    def __init__(self) -> None:
        self.friendly_scorer = FriendlyFraudScorer()
        self.subscription_scorer = SubscriptionAbuseScorer()

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        friendly_result = await self.friendly_scorer.score(event, features)
        subscription_result = await self.subscription_scorer.score(event, features)

        result = DetectionResult()
        result.reasons.extend(friendly_result.reasons)
        result.reasons.extend(subscription_result.reasons)
        result.score = max(friendly_result.score, subscription_result.score)
        result.triggered = result.score >= 0.3

        return result

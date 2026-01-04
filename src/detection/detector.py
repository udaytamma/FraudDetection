"""
Detection Engine

Orchestrates all detection modules and combines their results
into a unified detection result. Each detector runs independently
and produces signals that are aggregated here.

Design goals:
- Run detectors in parallel
- Aggregate signals with configurable weights
- Provide explainability (reasons for each signal)
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import PaymentEvent, FeatureSet, DecisionReason


@dataclass
class DetectionResult:
    """
    Result from a detection module.

    Contains the score and any triggered reasons for explainability.
    """
    score: float = 0.0  # 0.0 to 1.0
    triggered: bool = False
    reasons: list[DecisionReason] = field(default_factory=list)

    def add_reason(
        self,
        code: str,
        description: str,
        severity: str = "MEDIUM",
        value: Optional[str] = None,
        threshold: Optional[str] = None,
    ) -> None:
        """Add a reason for the detection."""
        self.reasons.append(
            DecisionReason(
                code=code,
                description=description,
                severity=severity,
                triggered_by=self.__class__.__name__ if hasattr(self, '__class__') else "Detector",
                value=value,
                threshold=threshold,
            )
        )


class BaseDetector(ABC):
    """
    Base class for all fraud detectors.

    Each detector focuses on a specific fraud pattern:
    - CardTestingDetector: Rapid small transactions to test cards
    - VelocityAttackDetector: Abnormal transaction velocity
    - GeoAnomalyDetector: Impossible travel, country mismatches
    - BotDetector: Emulators, datacenter IPs, automation signals
    """

    @abstractmethod
    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Run detection logic.

        Args:
            event: Payment event
            features: Computed feature set

        Returns:
            DetectionResult with score and reasons
        """
        pass


class DetectionEngine:
    """
    Orchestrates all detection modules.

    Runs detectors in parallel and combines results into
    an aggregated score with full explainability.
    """

    def __init__(self, detectors: list[BaseDetector]):
        """
        Initialize detection engine.

        Args:
            detectors: List of detector instances
        """
        self.detectors = detectors

    async def run_detection(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> tuple[dict[str, DetectionResult], list[DecisionReason]]:
        """
        Run all detectors and aggregate results.

        Args:
            event: Payment event
            features: Computed feature set

        Returns:
            Tuple of (results_by_detector, all_reasons)
        """
        # Run all detectors in parallel
        tasks = [
            detector.detect(event, features)
            for detector in self.detectors
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        results_by_detector: dict[str, DetectionResult] = {}
        all_reasons: list[DecisionReason] = []

        for detector, result in zip(self.detectors, results):
            detector_name = detector.__class__.__name__

            if isinstance(result, Exception):
                # Detector failed - log and continue with neutral result
                results_by_detector[detector_name] = DetectionResult(score=0.0)
                continue

            results_by_detector[detector_name] = result
            all_reasons.extend(result.reasons)

        return results_by_detector, all_reasons

    def compute_aggregate_scores(
        self,
        results: dict[str, DetectionResult],
    ) -> tuple[float, float]:
        """
        Compute aggregate criminal and friendly fraud scores.

        Args:
            results: Results by detector name

        Returns:
            Tuple of (criminal_score, friendly_score)
        """
        # Criminal fraud detectors
        criminal_detectors = [
            "CardTestingDetector",
            "VelocityAttackDetector",
            "GeoAnomalyDetector",
            "BotDetector",
        ]

        # Friendly fraud detectors (to be added)
        friendly_detectors = [
            "FriendlyFraudDetector",
        ]

        # Calculate criminal score (max of relevant detectors)
        criminal_scores = [
            results[name].score
            for name in criminal_detectors
            if name in results
        ]
        criminal_score = max(criminal_scores) if criminal_scores else 0.0

        # Calculate friendly score
        friendly_scores = [
            results[name].score
            for name in friendly_detectors
            if name in results
        ]
        friendly_score = max(friendly_scores) if friendly_scores else 0.0

        return criminal_score, friendly_score

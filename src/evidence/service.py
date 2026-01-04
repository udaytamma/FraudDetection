"""
Evidence Capture Service

Captures and stores transaction evidence for:
1. Dispute representment
2. Model training labels
3. Audit trail

Evidence is immutable once captured.
"""

from datetime import datetime, UTC
from typing import Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..config import settings
from ..schemas import (
    PaymentEvent,
    FeatureSet,
    RiskScores,
    FraudDecisionResponse,
)


class EvidenceService:
    """
    Service for capturing and storing transaction evidence.

    Evidence includes:
    - Transaction details
    - Device/geo/verification data
    - Features snapshot at decision time
    - Decision and scores
    """

    def __init__(self, database_url: str):
        """
        Initialize evidence service.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self.engine = None
        self.session_factory = None

    async def initialize(self) -> None:
        """Initialize database connection."""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=settings.app_debug,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        except Exception as e:
            print(f"WARNING: Database initialization failed: {e}")
            # Continue without database for testing

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()

    async def health_check(self) -> bool:
        """Check database connectivity."""
        if not self.session_factory:
            raise Exception("Database not initialized")

        async with self.session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1

    async def capture_evidence(
        self,
        event: PaymentEvent,
        features: FeatureSet,
        scores: RiskScores,
        response: FraudDecisionResponse,
        policy_version_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Capture transaction evidence.

        Evidence is captured immediately after decision and is immutable.
        This data is critical for dispute representment and training.

        Args:
            event: Original payment event
            features: Computed features
            scores: Risk scores
            response: Decision response
            policy_version_id: Database ID of the policy version used for decision

        Returns:
            Evidence ID if successful, None otherwise
        """
        if not self.session_factory:
            return None

        try:
            evidence_id = str(uuid4())

            # Build features snapshot
            features_snapshot = {
                "velocity": features.velocity.model_dump(),
                "entity": features.entity.model_dump(),
                "transaction": {
                    "amount_cents": features.amount_cents,
                    "is_high_value": features.is_high_value,
                    "is_recurring": features.is_recurring,
                    "has_3ds": features.has_3ds,
                    "channel": features.channel,
                    "avs_match": features.avs_match,
                    "cvv_match": features.cvv_match,
                },
            }

            # Build device fingerprint
            device_fingerprint = None
            if event.device:
                device_fingerprint = {
                    "device_id": event.device.device_id,
                    "device_type": event.device.device_type,
                    "os": event.device.os,
                    "os_version": event.device.os_version,
                    "browser": event.device.browser,
                    "browser_version": event.device.browser_version,
                    "is_emulator": event.device.is_emulator,
                    "is_rooted": event.device.is_rooted,
                    "screen_resolution": event.device.screen_resolution,
                    "timezone": event.device.timezone,
                    "language": event.device.language,
                }

            # Build decision reasons
            decision_reasons = [
                {
                    "code": r.code,
                    "description": r.description,
                    "severity": r.severity,
                }
                for r in response.reasons
            ]

            async with self.session_factory() as session:
                # Insert evidence record
                await session.execute(
                    text("""
                        INSERT INTO transaction_evidence (
                            id,
                            transaction_id,
                            idempotency_key,
                            captured_at,
                            amount_cents,
                            currency,
                            merchant_id,
                            merchant_name,
                            merchant_mcc,
                            card_token,
                            card_bin,
                            card_last_four,
                            device_id,
                            ip_address,
                            user_id,
                            risk_score,
                            criminal_score,
                            friendly_fraud_score,
                            decision,
                            decision_reasons,
                            features_snapshot,
                            avs_result,
                            cvv_result,
                            three_ds_result,
                            three_ds_version,
                            device_fingerprint,
                            geo_country,
                            geo_region,
                            geo_city,
                            policy_version,
                            policy_version_id
                        ) VALUES (
                            :id,
                            :transaction_id,
                            :idempotency_key,
                            :captured_at,
                            :amount_cents,
                            :currency,
                            :merchant_id,
                            :merchant_name,
                            :merchant_mcc,
                            :card_token,
                            :card_bin,
                            :card_last_four,
                            :device_id,
                            :ip_address,
                            :user_id,
                            :risk_score,
                            :criminal_score,
                            :friendly_fraud_score,
                            :decision,
                            :decision_reasons,
                            :features_snapshot,
                            :avs_result,
                            :cvv_result,
                            :three_ds_result,
                            :three_ds_version,
                            :device_fingerprint,
                            :geo_country,
                            :geo_region,
                            :geo_city,
                            :policy_version,
                            :policy_version_id
                        )
                    """),
                    {
                        "id": evidence_id,
                        "transaction_id": event.transaction_id,
                        "idempotency_key": event.idempotency_key,
                        "captured_at": datetime.now(UTC),
                        "amount_cents": event.amount_cents,
                        "currency": event.currency,
                        "merchant_id": event.merchant_id,
                        "merchant_name": event.merchant_name,
                        "merchant_mcc": event.merchant_mcc,
                        "card_token": event.card_token,
                        "card_bin": event.card_bin,
                        "card_last_four": event.card_last_four,
                        "device_id": event.device_id,
                        "ip_address": event.ip_address,
                        "user_id": event.user_id,
                        "risk_score": scores.risk_score,
                        "criminal_score": scores.criminal_score,
                        "friendly_fraud_score": scores.friendly_fraud_score,
                        "decision": response.decision.value,
                        "decision_reasons": str(decision_reasons),  # JSON
                        "features_snapshot": str(features_snapshot),  # JSON
                        "avs_result": event.verification.avs_result if event.verification else None,
                        "cvv_result": event.verification.cvv_result if event.verification else None,
                        "three_ds_result": event.verification.three_ds_result if event.verification else None,
                        "three_ds_version": event.verification.three_ds_version if event.verification else None,
                        "device_fingerprint": str(device_fingerprint) if device_fingerprint else None,
                        "geo_country": event.geo.country_code if event.geo else None,
                        "geo_region": event.geo.region if event.geo else None,
                        "geo_city": event.geo.city if event.geo else None,
                        "policy_version": response.policy_version,
                        "policy_version_id": policy_version_id,
                    },
                )
                await session.commit()

            return evidence_id

        except Exception as e:
            print(f"WARNING: Evidence capture failed: {e}")
            return None

    async def get_evidence(
        self,
        transaction_id: str,
    ) -> Optional[dict]:
        """
        Retrieve evidence for a transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            Evidence record as dict, or None if not found
        """
        if not self.session_factory:
            return None

        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT *
                    FROM transaction_evidence
                    WHERE transaction_id = :transaction_id
                """),
                {"transaction_id": transaction_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    async def record_chargeback(
        self,
        transaction_id: str,
        chargeback_id: str,
        amount_cents: int,
        reason_code: str,
        reason_description: Optional[str] = None,
        fraud_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Record a chargeback against a transaction.

        Used for:
        - Training labels
        - Updating entity risk profiles
        - Representment tracking

        Args:
            transaction_id: Original transaction ID
            chargeback_id: Chargeback identifier
            amount_cents: Chargeback amount
            reason_code: Network reason code
            reason_description: Human-readable reason
            fraud_type: Classification (CRIMINAL, FRIENDLY, MERCHANT_ERROR)

        Returns:
            Chargeback record ID if successful
        """
        if not self.session_factory:
            return None

        try:
            record_id = str(uuid4())

            async with self.session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO chargebacks (
                            id,
                            transaction_id,
                            chargeback_id,
                            received_at,
                            amount_cents,
                            currency,
                            reason_code,
                            reason_description,
                            fraud_type,
                            status
                        ) VALUES (
                            :id,
                            :transaction_id,
                            :chargeback_id,
                            :received_at,
                            :amount_cents,
                            :currency,
                            :reason_code,
                            :reason_description,
                            :fraud_type,
                            :status
                        )
                    """),
                    {
                        "id": record_id,
                        "transaction_id": transaction_id,
                        "chargeback_id": chargeback_id,
                        "received_at": datetime.now(UTC),
                        "amount_cents": amount_cents,
                        "currency": "USD",
                        "reason_code": reason_code,
                        "reason_description": reason_description,
                        "fraud_type": fraud_type,
                        "status": "RECEIVED",
                    },
                )
                await session.commit()

            return record_id

        except Exception as e:
            print(f"WARNING: Chargeback recording failed: {e}")
            return None

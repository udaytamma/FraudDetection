"""
Evidence Service Tests - Telco/MSP Payment Fraud

Tests for evidence capture and retrieval using mocked PostgreSQL.
These tests verify the service logic without requiring a live database.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from src.schemas import (
    PaymentEvent,
    FeatureSet,
    VelocityFeatures,
    EntityFeatures,
    RiskScores,
    FraudDecisionResponse,
    Decision,
)
from src.evidence.service import EvidenceService


class TestEvidenceServiceInit:
    """Tests for EvidenceService initialization."""

    def test_init_with_url(self):
        """Service should store the database URL."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        assert service.database_url == "postgresql+asyncpg://localhost/test"
        assert service.engine is None
        assert service.session_factory is None


class TestEvidenceCapture:
    """Tests for evidence capture logic."""

    @pytest_asyncio.fixture
    def mock_service(self):
        """Create service with mocked session factory."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        # Create mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Create async context manager
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Set up session factory to return our mock
        service.session_factory = MagicMock(return_value=mock_session)
        service._mock_session = mock_session  # Store for assertions

        return service

    @pytest.mark.asyncio
    async def test_capture_evidence_returns_id(
        self, mock_service, sample_event
    ):
        """capture_evidence should return a UUID string."""
        features = FeatureSet(
            velocity=VelocityFeatures(),
            entity=EntityFeatures(),
            amount_cents=2500,
        )
        scores = RiskScores(risk_score=0.15)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.ALLOW,
            scores=scores,
        )

        evidence_id = await mock_service.capture_evidence(
            event=sample_event,
            features=features,
            scores=scores,
            response=response,
        )

        assert evidence_id is not None
        assert len(evidence_id) == 36  # UUID format
        assert mock_service._mock_session.execute.call_count >= 1
        mock_service._mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_without_session_factory_returns_none(
        self, sample_event
    ):
        """capture_evidence should return None if not initialized."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")
        # session_factory is None (not initialized)

        features = FeatureSet(amount_cents=2500)
        scores = RiskScores(risk_score=0.15)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.ALLOW,
            scores=scores,
        )

        result = await service.capture_evidence(
            event=sample_event,
            features=features,
            scores=scores,
            response=response,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_capture_handles_db_error(
        self, mock_service, sample_event
    ):
        """capture_evidence should return None on database errors."""
        mock_service._mock_session.execute.side_effect = Exception("DB connection lost")

        features = FeatureSet(amount_cents=2500)
        scores = RiskScores(risk_score=0.5)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.REVIEW,
            scores=scores,
        )

        result = await mock_service.capture_evidence(
            event=sample_event,
            features=features,
            scores=scores,
            response=response,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_capture_with_no_device_info(
        self, mock_service, sample_event
    ):
        """Evidence capture should handle events with no device info."""
        sample_event.device = None

        features = FeatureSet(amount_cents=2500)
        scores = RiskScores(risk_score=0.15)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.ALLOW,
            scores=scores,
        )

        evidence_id = await mock_service.capture_evidence(
            event=sample_event,
            features=features,
            scores=scores,
            response=response,
        )

        assert evidence_id is not None

    @pytest.mark.asyncio
    async def test_capture_with_no_geo_info(
        self, mock_service, sample_event
    ):
        """Evidence capture should handle events with no geo info."""
        sample_event.geo = None

        features = FeatureSet(amount_cents=2500)
        scores = RiskScores(risk_score=0.15)
        response = FraudDecisionResponse(
            transaction_id=sample_event.transaction_id,
            idempotency_key=sample_event.idempotency_key,
            decision=Decision.ALLOW,
            scores=scores,
        )

        evidence_id = await mock_service.capture_evidence(
            event=sample_event,
            features=features,
            scores=scores,
            response=response,
        )

        assert evidence_id is not None


class TestEvidenceRetrieval:
    """Tests for evidence retrieval."""

    @pytest.mark.asyncio
    async def test_get_evidence_without_session_returns_none(self):
        """get_evidence should return None if not initialized."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        result = await service.get_evidence("txn_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_evidence_returns_dict(self):
        """get_evidence should return evidence as dict."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        # Mock session with a result row
        mock_row = {
            "id": "ev_123",
            "transaction_id": "txn_123",
            "decision": "ALLOW",
            "risk_score": 0.15,
        }
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = mock_row

        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        service.session_factory = MagicMock(return_value=mock_session)

        result = await service.get_evidence("txn_123")

        assert result is not None
        assert result["transaction_id"] == "txn_123"
        assert result["decision"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_get_evidence_not_found(self):
        """get_evidence should return None when transaction not found."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        mock_mappings = MagicMock()
        mock_mappings.first.return_value = None

        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        service.session_factory = MagicMock(return_value=mock_session)

        result = await service.get_evidence("nonexistent_txn")

        assert result is None


class TestChargebackRecording:
    """Tests for chargeback recording."""

    @pytest.mark.asyncio
    async def test_record_chargeback_without_session_returns_none(self):
        """record_chargeback should return None if not initialized."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        result = await service.record_chargeback(
            transaction_id="txn_123",
            chargeback_id="cb_456",
            amount_cents=5000,
            reason_code="10.4",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_record_chargeback_returns_id(self):
        """record_chargeback should return a UUID string."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        service.session_factory = MagicMock(return_value=mock_session)

        result = await service.record_chargeback(
            transaction_id="txn_123",
            chargeback_id="cb_456",
            amount_cents=5000,
            reason_code="10.4",
            reason_description="Fraud - Card Not Present",
            fraud_type="CRIMINAL",
        )

        assert result is not None
        assert len(result) == 36  # UUID format
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_chargeback_handles_db_error(self):
        """record_chargeback should return None on database error."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        service.session_factory = MagicMock(return_value=mock_session)

        result = await service.record_chargeback(
            transaction_id="txn_123",
            chargeback_id="cb_456",
            amount_cents=5000,
            reason_code="10.4",
        )

        assert result is None


class TestHealthCheck:
    """Tests for database health check."""

    @pytest.mark.asyncio
    async def test_health_check_no_session_raises(self):
        """Health check should raise if not initialized."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        with pytest.raises(Exception, match="Database not initialized"):
            await service.health_check()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check should return True on successful SELECT 1."""
        service = EvidenceService(database_url="postgresql+asyncpg://localhost/test")

        mock_result = MagicMock()
        mock_result.scalar.return_value = 1

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        service.session_factory = MagicMock(return_value=mock_session)

        result = await service.health_check()

        assert result is True

"""
API Tests

Integration tests for the fraud detection API.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from src.schemas import PaymentEvent


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_status(self, api_client: AsyncClient):
        """Test health endpoint returns status."""
        response = await api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded")


class TestDecisionEndpoint:
    """Tests for decision endpoint."""

    @pytest.mark.asyncio
    async def test_minimal_request(self, api_client: AsyncClient):
        """Test decision with minimal request (telco SIM activation)."""
        payload = {
            "transaction_id": "txn_test_123",
            "idempotency_key": "idem_test_123",
            "amount_cents": 2500,  # $25 SIM activation
            "card_token": "card_test_123",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "event_subtype": "sim_activation",
        }

        response = await api_client.post("/decide", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["transaction_id"] == "txn_test_123"
        assert data["decision"] in ("ALLOW", "FRICTION", "REVIEW", "BLOCK")
        assert "scores" in data
        assert "processing_time_ms" in data

    @pytest.mark.asyncio
    async def test_full_request(self, api_client: AsyncClient, sample_event: PaymentEvent):
        """Test decision with full request."""
        payload = sample_event.model_dump(mode="json")

        response = await api_client.post("/decide", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] in ("ALLOW", "FRICTION", "REVIEW", "BLOCK")

    @pytest.mark.asyncio
    async def test_idempotency(self, api_client: AsyncClient):
        """Test idempotency returns cached result."""
        payload = {
            "transaction_id": "txn_idem_test",
            "idempotency_key": "idem_idem_test",
            "amount_cents": 2000,  # $20 topup
            "card_token": "card_idem_test",
            "service_id": "mobile_prepaid_001",
            "event_subtype": "topup",
        }

        # First request
        response1 = await api_client.post("/decide", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with same idempotency key
        response2 = await api_client.post("/decide", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()

        # Should return cached result
        assert data1["decision"] == data2["decision"]
        assert data2["is_cached"] is True

    @pytest.mark.asyncio
    async def test_high_risk_blocked(self, api_client: AsyncClient):
        """Test high-risk transaction gets blocked (device upgrade fraud)."""
        payload = {
            "transaction_id": "txn_high_risk",
            "idempotency_key": "idem_high_risk",
            "amount_cents": 120000,  # $1200 device upgrade
            "card_token": "card_high_risk",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "event_subtype": "device_upgrade",  # High-risk event
            "device": {
                "device_id": "dev_high_risk",
                "is_emulator": True,  # High-risk signal (SIM farm indicator)
            },
            "geo": {
                "ip_address": "1.2.3.4",
                "is_tor": True,  # High-risk signal
            },
        }

        response = await api_client.post("/decide", json=payload)

        assert response.status_code == 200
        data = response.json()
        # Emulator + Tor + device upgrade should trigger block
        assert data["decision"] in ("BLOCK", "REVIEW")
        assert len(data["reasons"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_request_rejected(self, api_client: AsyncClient):
        """Test invalid request is rejected."""
        payload = {
            # Missing required fields
            "amount_cents": 5000,
        }

        response = await api_client.post("/decide", json=payload)

        assert response.status_code == 422  # Validation error


class TestPolicyEndpoint:
    """Tests for policy endpoints."""

    @pytest.mark.asyncio
    async def test_get_policy_version(self, api_client: AsyncClient):
        """Test getting policy version."""
        response = await api_client.get("/policy/version")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "hash" in data

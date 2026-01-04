"""
Pytest Configuration and Fixtures

Provides shared fixtures for fraud detection tests.
"""

import asyncio
from datetime import datetime, UTC
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.config import settings
from src.schemas import (
    PaymentEvent,
    DeviceInfo,
    GeoInfo,
    VerificationInfo,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """
    Get Redis client for tests.

    Uses test-specific key prefix to avoid conflicts.
    """
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True,
    )

    try:
        await client.ping()
        yield client
    except Exception:
        pytest.skip("Redis not available")
    finally:
        # Cleanup test keys
        keys = await client.keys(f"{settings.redis_key_prefix}*")
        if keys:
            await client.delete(*keys)
        await client.close()


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Get async HTTP client for API tests.

    Uses lifespan context manager to properly initialize app resources.
    """
    from src.api.main import lifespan

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def sample_event() -> PaymentEvent:
    """
    Create a sample payment event for testing.
    """
    return PaymentEvent(
        transaction_id=f"txn_{uuid4().hex[:16]}",
        idempotency_key=f"idem_{uuid4().hex[:16]}",
        amount_cents=5000,  # $50
        currency="USD",
        card_token=f"card_{uuid4().hex[:16]}",
        card_bin="411111",
        card_last_four="1234",
        card_brand="Visa",
        card_type="credit",
        card_country="US",
        merchant_id="merchant_123",
        merchant_name="Test Merchant",
        merchant_mcc="5411",
        merchant_country="US",
        user_id="user_123",
        account_age_days=30,
        is_guest=False,
        device=DeviceInfo(
            device_id=f"dev_{uuid4().hex[:16]}",
            device_type="mobile",
            os="iOS",
            os_version="17.0",
            browser="Safari",
            browser_version="17.0",
            is_emulator=False,
            is_rooted=False,
            screen_resolution="1170x2532",
            timezone="America/New_York",
            language="en-US",
        ),
        geo=GeoInfo(
            ip_address="192.168.1.100",
            country_code="US",
            region="New York",
            city="New York",
            latitude=40.7128,
            longitude=-74.0060,
            is_vpn=False,
            is_proxy=False,
            is_datacenter=False,
            is_tor=False,
        ),
        verification=VerificationInfo(
            avs_result="Y",
            cvv_result="M",
            three_ds_result="Y",
            three_ds_version="2.2",
            three_ds_eci="05",
        ),
        channel="mobile",
        is_recurring=False,
        session_id=f"sess_{uuid4().hex[:16]}",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def high_risk_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a high-risk payment event for testing.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 200000  # $2000
    event.device.is_emulator = True
    event.geo.is_datacenter = True
    event.geo.is_tor = True
    event.account_age_days = 1
    return event


@pytest.fixture
def card_testing_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a card testing attack event for testing.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 100  # $1 - small test amount
    return event


@pytest.fixture
def friendly_fraud_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a friendly fraud risk event for testing.
    """
    event = sample_event.model_copy(deep=True)
    # Would need to set up user profile with chargeback history
    return event

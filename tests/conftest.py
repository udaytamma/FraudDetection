"""
Pytest Configuration and Fixtures - Telco/MSP Payment Fraud

Provides shared fixtures for telco fraud detection tests.
"""

import asyncio
import os
from datetime import datetime, UTC
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
import redis.asyncio as redis
import asyncpg
import httpx
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.config import settings
from src.schemas import (
    PaymentEvent,
    DeviceInfo,
    GeoInfo,
    VerificationInfo,
    ServiceType,
    EventSubtype,
)


def pytest_configure(config):
    config.addinivalue_line("markers", "sanity: sanity test suite")
    config.addinivalue_line("markers", "unit: unit tests (no infrastructure)")
    config.addinivalue_line("markers", "integration: integration tests (requires Docker)")
    config.addinivalue_line("markers", "system: system tests (requires running services)")


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
    Create a sample telco payment event for testing.
    Mobile SIM activation scenario.
    """
    return PaymentEvent(
        transaction_id=f"txn_{uuid4().hex[:16]}",
        idempotency_key=f"idem_{uuid4().hex[:16]}",
        amount_cents=2500,  # $25 SIM activation fee
        currency="USD",
        card_token=f"card_{uuid4().hex[:16]}",
        card_bin="411111",
        card_last_four="1234",
        card_brand="Visa",
        card_type="credit",
        card_country="US",
        # Telco-specific fields
        service_id="mobile_prepaid_001",
        service_name="Telco Mobile Prepaid",
        service_type=ServiceType.MOBILE,
        service_region="US",
        event_subtype=EventSubtype.SIM_ACTIVATION,
        subscriber_id="subscriber_123",
        phone_number="15551234567",
        imei="353456789012345",
        sim_iccid="89012600001234567890",
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
    Device upgrade from new subscriber with suspicious signals.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 120000  # $1200 device upgrade
    event.event_subtype = EventSubtype.DEVICE_UPGRADE
    event.device.is_emulator = True
    event.geo.is_datacenter = True
    event.geo.is_tor = True
    event.account_age_days = 1  # New subscriber
    return event


@pytest.fixture(scope="session")
def sanity_api_url() -> str:
    return os.environ.get("SANITY_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def sanity_api_token() -> str | None:
    return os.environ.get("SANITY_API_TOKEN") or None


@pytest.fixture(scope="session")
def sanity_dashboard_url() -> str:
    return os.environ.get("SANITY_DASHBOARD_URL", "http://localhost:8501")


@pytest.fixture(scope="session")
def sanity_headers(sanity_api_token: str | None) -> dict:
    return {"X-API-Key": sanity_api_token} if sanity_api_token else {}


@pytest_asyncio.fixture(scope="session")
async def system_client(sanity_api_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=sanity_api_url, timeout=5.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def check_api_available(system_client: httpx.AsyncClient, sanity_headers: dict, sanity_api_url: str):
    try:
        resp = await system_client.get("/health", headers=sanity_headers)
        if resp.status_code != 200:
            pytest.skip(f"API not available at {sanity_api_url}")
    except httpx.RequestError:
        pytest.skip(f"API not available at {sanity_api_url}")


@pytest.fixture
def clean_transaction_payload() -> dict:
    unique = uuid4().hex[:12]
    return {
        "transaction_id": f"txn_{unique}",
        "idempotency_key": f"idem_{unique}",
        "amount_cents": 2500,
        "currency": "USD",
        "card_token": f"card_{unique}",
        "card_bin": "411111",
        "card_last_four": "4242",
        "service_id": "mobile_topup_001",
        "service_name": "Mobile Topup",
        "service_type": "mobile",
        "event_subtype": "topup",
        "user_id": f"user_{unique}",
        "account_age_days": 30,
        "is_guest": False,
    }


@pytest.fixture
def high_risk_transaction_payload() -> dict:
    unique = uuid4().hex[:12]
    return {
        "transaction_id": f"txn_{unique}",
        "idempotency_key": f"idem_{unique}",
        "amount_cents": 120000,
        "currency": "USD",
        "card_token": f"card_{unique}",
        "card_bin": "411111",
        "card_last_four": "9999",
        "service_id": "device_upgrade_001",
        "service_name": "Device Upgrade",
        "service_type": "mobile",
        "event_subtype": "device_upgrade",
        "user_id": f"user_{unique}",
        "account_age_days": 1,
        "is_guest": False,
        "device": {
            "device_id": f"dev_{unique}",
            "device_type": "mobile",
            "os": "Android",
            "os_version": "14",
            "browser": "Chrome",
            "browser_version": "120",
            "is_emulator": True,
            "is_rooted": False,
        },
        "geo": {
            "ip_address": "203.0.113.10",
            "country_code": "US",
            "region": "CA",
            "city": "San Francisco",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "is_vpn": False,
            "is_proxy": False,
            "is_datacenter": False,
            "is_tor": True,
        },
    }


@pytest_asyncio.fixture
async def pg_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    postgres_url = os.environ.get("POSTGRES_URL") or settings.postgres_sync_url
    if postgres_url.startswith("postgresql+asyncpg://"):
        postgres_url = postgres_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        conn = await asyncpg.connect(postgres_url)
        yield conn
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        if "conn" in locals():
            await conn.close()


@pytest.fixture
def card_testing_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a card testing attack event for testing.
    Small topup to test card validity.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 500  # $5 topup - small test amount
    event.event_subtype = EventSubtype.TOPUP
    return event


@pytest.fixture
def sim_farm_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a SIM farm attack event for testing.
    Multiple SIM activations from same card.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 0  # Free SIM activation
    event.event_subtype = EventSubtype.SIM_ACTIVATION
    event.device.is_emulator = True  # Common in SIM farms
    return event


@pytest.fixture
def device_upgrade_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a device upgrade event for testing.
    High-value subsidized device purchase.
    """
    event = sample_event.model_copy(deep=True)
    event.amount_cents = 99900  # $999 device
    event.event_subtype = EventSubtype.DEVICE_UPGRADE
    event.imei = "353456789099999"  # Different IMEI
    return event


@pytest.fixture
def friendly_fraud_event(sample_event: PaymentEvent) -> PaymentEvent:
    """
    Create a friendly fraud risk event for testing.
    Device upgrade from subscriber with prior chargebacks.
    """
    event = sample_event.model_copy(deep=True)
    event.event_subtype = EventSubtype.DEVICE_UPGRADE
    event.amount_cents = 99900  # $999 device
    # Would need to set up subscriber profile with chargeback history
    return event

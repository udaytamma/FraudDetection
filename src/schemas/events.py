"""
Payment Event Schemas

Defines the canonical PaymentEvent structure for all incoming
transaction requests. This is the primary input to the fraud
detection pipeline.
"""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class EventType(str, Enum):
    """
    Payment event types in the transaction lifecycle.

    - AUTHORIZATION: Initial payment request (requires <200ms decision)
    - CAPTURE: Money actually moves (async processing)
    - REFUND: Customer-initiated reversal (async processing)
    - CHARGEBACK: Dispute filed by cardholder (batch processing)
    """
    AUTHORIZATION = "authorization"
    CAPTURE = "capture"
    REFUND = "refund"
    CHARGEBACK = "chargeback"


class DeviceInfo(BaseModel):
    """
    Device fingerprint information.

    Captures device characteristics for fraud detection.
    Emulators and rooted devices are high-risk signals.
    """
    device_id: str = Field(
        ...,
        description="Unique device identifier (fingerprint hash)",
        min_length=1,
        max_length=64,
    )
    device_type: Optional[str] = Field(
        default=None,
        description="Device type: mobile, desktop, tablet",
    )
    os: Optional[str] = Field(
        default=None,
        description="Operating system",
    )
    os_version: Optional[str] = Field(
        default=None,
        description="OS version",
    )
    browser: Optional[str] = Field(
        default=None,
        description="Browser name",
    )
    browser_version: Optional[str] = Field(
        default=None,
        description="Browser version",
    )
    is_emulator: bool = Field(
        default=False,
        description="True if device appears to be an emulator",
    )
    is_rooted: bool = Field(
        default=False,
        description="True if device appears to be rooted/jailbroken",
    )
    screen_resolution: Optional[str] = Field(
        default=None,
        description="Screen resolution (e.g., '1920x1080')",
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Device timezone",
    )
    language: Optional[str] = Field(
        default=None,
        description="Device language setting",
    )


class GeoInfo(BaseModel):
    """
    Geographic information from IP address.

    Used for impossible travel detection and geo-based rules.
    """
    ip_address: str = Field(
        ...,
        description="Client IP address",
    )
    country_code: Optional[str] = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country code",
        max_length=2,
    )
    region: Optional[str] = Field(
        default=None,
        description="Region/state/province",
    )
    city: Optional[str] = Field(
        default=None,
        description="City name",
    )
    latitude: Optional[float] = Field(
        default=None,
        description="Latitude coordinate",
        ge=-90,
        le=90,
    )
    longitude: Optional[float] = Field(
        default=None,
        description="Longitude coordinate",
        ge=-180,
        le=180,
    )
    is_vpn: bool = Field(
        default=False,
        description="True if IP appears to be a VPN",
    )
    is_proxy: bool = Field(
        default=False,
        description="True if IP appears to be a proxy",
    )
    is_datacenter: bool = Field(
        default=False,
        description="True if IP is from a datacenter (not residential)",
    )
    is_tor: bool = Field(
        default=False,
        description="True if IP is a Tor exit node",
    )


class VerificationInfo(BaseModel):
    """
    Card verification results from payment processor.

    These signals are critical for criminal fraud detection
    and evidence collection for disputes.
    """
    avs_result: Optional[str] = Field(
        default=None,
        description="Address Verification Service result code",
    )
    cvv_result: Optional[str] = Field(
        default=None,
        description="CVV verification result code",
    )
    three_ds_result: Optional[str] = Field(
        default=None,
        description="3D Secure authentication result",
    )
    three_ds_version: Optional[str] = Field(
        default=None,
        description="3D Secure version (1.0, 2.0, 2.1, 2.2)",
    )
    three_ds_eci: Optional[str] = Field(
        default=None,
        description="Electronic Commerce Indicator from 3DS",
    )


class PaymentEvent(BaseModel):
    """
    Canonical Payment Event Schema.

    This is the primary input to the fraud detection pipeline.
    All fields are captured for evidence and training purposes.

    Key design decisions:
    - card_token (not raw PAN) for PCI compliance
    - idempotency_key for exactly-once processing
    - All amounts in cents to avoid floating point issues
    - Timestamps in UTC with timezone awareness
    """

    # =========================================================================
    # Identifiers
    # =========================================================================
    transaction_id: str = Field(
        ...,
        description="Unique transaction identifier from payment processor",
        min_length=1,
        max_length=64,
    )
    idempotency_key: str = Field(
        ...,
        description="Client-provided idempotency key for exactly-once processing",
        min_length=1,
        max_length=128,
    )
    event_type: EventType = Field(
        default=EventType.AUTHORIZATION,
        description="Type of payment event",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="Event timestamp in UTC",
    )

    # =========================================================================
    # Transaction Details
    # =========================================================================
    amount_cents: int = Field(
        ...,
        description="Transaction amount in cents",
        ge=0,
    )
    currency: str = Field(
        default="USD",
        description="ISO 4217 currency code",
        min_length=3,
        max_length=3,
    )

    # =========================================================================
    # Card Information (Tokenized for PCI compliance)
    # =========================================================================
    card_token: str = Field(
        ...,
        description="Tokenized card identifier (not raw PAN)",
        min_length=1,
        max_length=64,
    )
    card_bin: Optional[str] = Field(
        default=None,
        description="First 6-8 digits of card (BIN/IIN)",
        min_length=6,
        max_length=8,
    )
    card_last_four: Optional[str] = Field(
        default=None,
        description="Last 4 digits of card",
        min_length=4,
        max_length=4,
    )
    card_brand: Optional[str] = Field(
        default=None,
        description="Card brand (Visa, Mastercard, Amex, etc.)",
    )
    card_type: Optional[str] = Field(
        default=None,
        description="Card type (credit, debit, prepaid)",
    )
    card_country: Optional[str] = Field(
        default=None,
        description="Card issuing country code",
        max_length=2,
    )

    # =========================================================================
    # Merchant Information
    # =========================================================================
    merchant_id: str = Field(
        ...,
        description="Merchant identifier",
        min_length=1,
        max_length=64,
    )
    merchant_name: Optional[str] = Field(
        default=None,
        description="Merchant display name",
        max_length=256,
    )
    merchant_mcc: Optional[str] = Field(
        default=None,
        description="Merchant Category Code",
        min_length=4,
        max_length=4,
    )
    merchant_country: Optional[str] = Field(
        default=None,
        description="Merchant country code",
        max_length=2,
    )

    # =========================================================================
    # User/Account Information
    # =========================================================================
    user_id: Optional[str] = Field(
        default=None,
        description="User/account identifier",
        max_length=64,
    )
    account_age_days: Optional[int] = Field(
        default=None,
        description="Days since account creation",
        ge=0,
    )
    is_guest: bool = Field(
        default=False,
        description="True if guest checkout (no account)",
    )

    # =========================================================================
    # Device and Geo Information
    # =========================================================================
    device: Optional[DeviceInfo] = Field(
        default=None,
        description="Device fingerprint information",
    )
    geo: Optional[GeoInfo] = Field(
        default=None,
        description="Geographic information",
    )

    # =========================================================================
    # Verification Results
    # =========================================================================
    verification: Optional[VerificationInfo] = Field(
        default=None,
        description="Card verification results",
    )

    # =========================================================================
    # Additional Context
    # =========================================================================
    channel: Optional[str] = Field(
        default=None,
        description="Transaction channel (web, mobile, api, pos)",
    )
    is_recurring: bool = Field(
        default=False,
        description="True if this is a recurring/subscription payment",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Web/app session identifier",
        max_length=128,
    )

    # =========================================================================
    # Validators
    # =========================================================================
    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Ensure currency is uppercase."""
        return v.upper()

    @field_validator("card_bin")
    @classmethod
    def validate_card_bin(cls, v: Optional[str]) -> Optional[str]:
        """Ensure BIN contains only digits."""
        if v is not None and not v.isdigit():
            raise ValueError("card_bin must contain only digits")
        return v

    @field_validator("merchant_mcc")
    @classmethod
    def validate_mcc(cls, v: Optional[str]) -> Optional[str]:
        """Ensure MCC contains only digits."""
        if v is not None and not v.isdigit():
            raise ValueError("merchant_mcc must contain only digits")
        return v

    @property
    def amount_dollars(self) -> Decimal:
        """Convert cents to dollars."""
        return Decimal(self.amount_cents) / 100

    @property
    def is_high_value(self) -> bool:
        """Check if transaction exceeds high-value threshold ($1000)."""
        return self.amount_cents >= 100000  # $1000 in cents

    @property
    def has_3ds(self) -> bool:
        """Check if 3D Secure was used."""
        return (
            self.verification is not None
            and self.verification.three_ds_result is not None
        )

    @property
    def ip_address(self) -> Optional[str]:
        """Convenience property to get IP address."""
        return self.geo.ip_address if self.geo else None

    @property
    def device_id(self) -> Optional[str]:
        """Convenience property to get device ID."""
        return self.device.device_id if self.device else None

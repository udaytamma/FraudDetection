"""
Payment Event Schemas for Telco/MSP Payment Fraud Detection

Defines the canonical PaymentEvent structure for all incoming
transaction requests. This is the primary input to the fraud
detection pipeline.

Supports two service verticals:
- Mobile: SIM activations, top-ups, device upgrades
- Broadband: Service activations, equipment purchases
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


class ServiceType(str, Enum):
    """
    Telco/MSP service verticals.

    Each service type has different fraud patterns and risk profiles.
    """
    MOBILE = "mobile"
    BROADBAND = "broadband"


class EventSubtype(str, Enum):
    """
    High-fraud-risk event subtypes within each service vertical.

    Mobile subtypes:
    - sim_activation: New SIM card activation (SIM farm risk)
    - sim_swap: SIM change on existing number (account takeover)
    - device_upgrade: Subsidized device purchase (resale fraud)
    - topup: Prepaid balance reload (stolen card testing)
    - international_enable: International roaming activation (IRSF setup)

    Broadband subtypes:
    - service_activation: New broadband service (promo abuse)
    - equipment_swap: Modem/router replacement (equipment fraud)
    - speed_upgrade: Bandwidth tier upgrade (promo abuse)
    - equipment_purchase: CPE purchase (resale fraud)
    """
    # Mobile
    SIM_ACTIVATION = "sim_activation"
    SIM_SWAP = "sim_swap"
    DEVICE_UPGRADE = "device_upgrade"
    TOPUP = "topup"
    INTERNATIONAL_ENABLE = "international_enable"

    # Broadband
    SERVICE_ACTIVATION = "service_activation"
    EQUIPMENT_SWAP = "equipment_swap"
    SPEED_UPGRADE = "speed_upgrade"
    EQUIPMENT_PURCHASE = "equipment_purchase"


class DeviceInfo(BaseModel):
    """
    Device fingerprint information.

    Captures device characteristics for payment fraud detection.
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

    These signals are critical for criminal payment fraud detection
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
    Canonical Payment Event Schema for Telco/MSP Payment Fraud Detection.

    This is the primary input to the fraud detection pipeline.
    All fields are captured for evidence and training purposes.

    Key design decisions:
    - card_token (not raw PAN) for PCI compliance
    - idempotency_key for exactly-once processing
    - All amounts in cents to avoid floating point issues
    - Timestamps in UTC with timezone awareness
    - Service-specific identifiers for telco context
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
    # Service Information (Telco/MSP specific)
    # =========================================================================
    service_id: str = Field(
        ...,
        description="Service identifier (e.g., mobile_prepaid_001)",
        min_length=1,
        max_length=64,
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Service display name (e.g., 'Mobile Prepaid', 'Fiber 1Gbps')",
        max_length=256,
    )
    service_type: ServiceType = Field(
        default=ServiceType.MOBILE,
        description="Service vertical: mobile or broadband",
    )
    event_subtype: EventSubtype = Field(
        default=EventSubtype.TOPUP,
        description="Specific action within the service type",
    )
    service_region: Optional[str] = Field(
        default=None,
        description="Service operating region/country code",
        max_length=2,
    )

    # =========================================================================
    # Subscriber Information
    # =========================================================================
    subscriber_id: Optional[str] = Field(
        default=None,
        description="Subscriber/customer account identifier",
        max_length=64,
    )
    user_id: Optional[str] = Field(
        default=None,
        description="User/account identifier (may differ from subscriber)",
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
    # Mobile-Specific Identifiers
    # =========================================================================
    phone_number: Optional[str] = Field(
        default=None,
        description="MSISDN (phone number) for mobile services",
        max_length=20,
    )
    imei: Optional[str] = Field(
        default=None,
        description="Device IMEI for mobile services",
        max_length=20,
    )
    sim_iccid: Optional[str] = Field(
        default=None,
        description="SIM card ICCID for mobile services",
        max_length=22,
    )

    # =========================================================================
    # Broadband-Specific Identifiers
    # =========================================================================
    modem_mac: Optional[str] = Field(
        default=None,
        description="Cable modem MAC address for broadband services",
        max_length=17,
    )
    cpe_serial: Optional[str] = Field(
        default=None,
        description="Customer premises equipment serial number",
        max_length=64,
    )
    service_address_hash: Optional[str] = Field(
        default=None,
        description="Hashed service installation address",
        max_length=64,
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
        description="Transaction channel (web, mobile_app, api, retail, call_center)",
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

    @property
    def is_high_risk_subtype(self) -> bool:
        """Check if event subtype is high-risk for payment fraud."""
        high_risk = {
            EventSubtype.DEVICE_UPGRADE,
            EventSubtype.SIM_SWAP,
            EventSubtype.INTERNATIONAL_ENABLE,
            EventSubtype.EQUIPMENT_PURCHASE,
        }
        return self.event_subtype in high_risk

    @property
    def is_mobile(self) -> bool:
        """Check if this is a mobile service event."""
        return self.service_type == ServiceType.MOBILE

    @property
    def is_broadband(self) -> bool:
        """Check if this is a broadband service event."""
        return self.service_type == ServiceType.BROADBAND


class ChargebackRequest(BaseModel):
    """
    Chargeback ingestion request.

    Used to record chargebacks against transactions and update entity
    risk profiles for future fraud scoring.
    """
    transaction_id: str = Field(
        ...,
        description="Original transaction ID the chargeback is against",
        min_length=1,
        max_length=64,
    )
    chargeback_id: str = Field(
        ...,
        description="Unique chargeback identifier from the network",
        min_length=1,
        max_length=64,
    )
    amount_cents: int = Field(
        ...,
        description="Chargeback amount in cents (may differ from original)",
        ge=0,
    )
    reason_code: str = Field(
        ...,
        description="Network reason code (e.g., Visa 10.4, MC 4837)",
        min_length=1,
        max_length=20,
    )
    reason_description: Optional[str] = Field(
        default=None,
        description="Human-readable reason description",
        max_length=256,
    )
    fraud_type: Optional[str] = Field(
        default=None,
        description="Fraud classification: CRIMINAL, FRIENDLY, MERCHANT_ERROR, UNKNOWN",
    )

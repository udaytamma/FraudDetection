"""
Entity Profile Schemas

Defines the profile structures for each entity type tracked
by the fraud detection system. Entity profiles store aggregated
features computed from transaction history.

Entity types follow the money flow:
- Card: The payment instrument (stolen, enumerated, tested)
- Device: The access point (shared by fraud rings, emulated)
- IP: The network address (proxied, VPN, datacenter)
- User: The account (fake, ATO, friendly fraud)
- Merchant: The seller (collusion, high-risk MCC)
"""

from datetime import datetime, UTC
from typing import Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class CardProfile(BaseModel):
    """
    Card entity profile.

    Tracks velocity and risk metrics for a tokenized card.
    High-risk signals: high attempt count, high decline rate,
    many distinct merchants in short time.
    """
    card_token: str = Field(
        ...,
        description="Tokenized card identifier",
    )

    # Timestamps
    first_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this card was first seen",
    )
    last_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this card was last seen",
    )
    last_geo_seen: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last geo observation for this card",
    )
    last_geo_lat: Optional[float] = Field(
        default=None,
        description="Last known latitude for this card",
    )
    last_geo_lon: Optional[float] = Field(
        default=None,
        description="Last known longitude for this card",
    )

    # Velocity counters (sliding windows)
    attempts_10m: int = Field(
        default=0,
        description="Transaction attempts in last 10 minutes",
    )
    attempts_1h: int = Field(
        default=0,
        description="Transaction attempts in last 1 hour",
    )
    attempts_24h: int = Field(
        default=0,
        description="Transaction attempts in last 24 hours",
    )

    # Decline tracking
    declines_10m: int = Field(
        default=0,
        description="Declined transactions in last 10 minutes",
    )
    declines_1h: int = Field(
        default=0,
        description="Declined transactions in last 1 hour",
    )

    # Distinct entity counts
    distinct_accounts_24h: int = Field(
        default=0,
        description="Distinct accounts/services in last 24 hours",
    )
    distinct_devices_24h: int = Field(
        default=0,
        description="Distinct devices in last 24 hours",
    )
    distinct_ips_24h: int = Field(
        default=0,
        description="Distinct IPs in last 24 hours",
    )

    # Historical aggregates
    total_transactions: int = Field(
        default=0,
        description="Total transaction count (all time)",
    )
    chargeback_count: int = Field(
        default=0,
        description="Total chargebacks on this card",
    )

    @property
    def decline_rate_10m(self) -> float:
        """Calculate decline rate in 10-minute window."""
        if self.attempts_10m == 0:
            return 0.0
        return self.declines_10m / self.attempts_10m


class DeviceProfile(BaseModel):
    """
    Device entity profile.

    Tracks behavior patterns for a device fingerprint.
    High-risk signals: many distinct cards, emulator/rooted,
    inconsistent geo patterns.
    """
    device_id: str = Field(
        ...,
        description="Device fingerprint identifier",
    )

    # Timestamps
    first_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this device was first seen",
    )
    last_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this device was last seen",
    )

    # Device characteristics (from fingerprint)
    is_emulator: bool = Field(
        default=False,
        description="Device appears to be an emulator",
    )
    is_rooted: bool = Field(
        default=False,
        description="Device appears to be rooted/jailbroken",
    )

    # Velocity counters
    attempts_1h: int = Field(
        default=0,
        description="Transaction attempts in last 1 hour",
    )
    attempts_24h: int = Field(
        default=0,
        description="Transaction attempts in last 24 hours",
    )

    # Distinct card tracking (critical for fraud ring detection)
    distinct_cards_1h: int = Field(
        default=0,
        description="Distinct cards used from this device in last 1 hour",
    )
    distinct_cards_24h: int = Field(
        default=0,
        description="Distinct cards used from this device in last 24 hours",
    )

    # User tracking
    distinct_users_24h: int = Field(
        default=0,
        description="Distinct users from this device in last 24 hours",
    )

    # Historical aggregates
    total_transactions: int = Field(
        default=0,
        description="Total transaction count (all time)",
    )
    chargeback_count: int = Field(
        default=0,
        description="Total chargebacks from this device",
    )

    # Last known location
    last_country: Optional[str] = Field(
        default=None,
        description="Last known country code",
    )
    last_city: Optional[str] = Field(
        default=None,
        description="Last known city",
    )


class IPProfile(BaseModel):
    """
    IP address entity profile.

    Tracks behavior patterns for an IP address.
    High-risk signals: datacenter IP, VPN/proxy, many distinct cards,
    Tor exit node.
    """
    ip_address: str = Field(
        ...,
        description="IP address",
    )

    # Timestamps
    first_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this IP was first seen",
    )
    last_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this IP was last seen",
    )

    # IP characteristics
    is_datacenter: bool = Field(
        default=False,
        description="IP is from a datacenter (not residential)",
    )
    is_vpn: bool = Field(
        default=False,
        description="IP appears to be a VPN",
    )
    is_proxy: bool = Field(
        default=False,
        description="IP appears to be a proxy",
    )
    is_tor: bool = Field(
        default=False,
        description="IP is a Tor exit node",
    )

    # Geo data
    country_code: Optional[str] = Field(
        default=None,
        description="Country code",
    )
    region: Optional[str] = Field(
        default=None,
        description="Region/state",
    )
    city: Optional[str] = Field(
        default=None,
        description="City",
    )

    # Velocity counters
    attempts_1h: int = Field(
        default=0,
        description="Transaction attempts in last 1 hour",
    )
    attempts_24h: int = Field(
        default=0,
        description="Transaction attempts in last 24 hours",
    )

    # Distinct card tracking
    distinct_cards_1h: int = Field(
        default=0,
        description="Distinct cards from this IP in last 1 hour",
    )
    distinct_cards_24h: int = Field(
        default=0,
        description="Distinct cards from this IP in last 24 hours",
    )

    # Historical aggregates
    total_transactions: int = Field(
        default=0,
        description="Total transaction count (all time)",
    )
    chargeback_count: int = Field(
        default=0,
        description="Total chargebacks from this IP",
    )


class UserProfile(BaseModel):
    """
    User/Account entity profile.

    Tracks behavior patterns for a user account.
    Key for friendly fraud detection: past disputes, refund gaming,
    account age, chargeback history.
    """
    user_id: str = Field(
        ...,
        description="User/account identifier",
    )

    # Account metadata
    account_created: Optional[datetime] = Field(
        default=None,
        description="When the account was created",
    )
    account_age_days: int = Field(
        default=0,
        description="Days since account creation",
    )

    # Timestamps
    first_transaction: Optional[datetime] = Field(
        default=None,
        description="First transaction timestamp",
    )
    last_transaction: Optional[datetime] = Field(
        default=None,
        description="Last transaction timestamp",
    )

    # Risk tier (computed from historical behavior)
    risk_tier: str = Field(
        default="NORMAL",
        description="User risk tier: LOW, NORMAL, ELEVATED, HIGH",
    )

    # Velocity counters
    transactions_24h: int = Field(
        default=0,
        description="Transactions in last 24 hours",
    )
    transactions_7d: int = Field(
        default=0,
        description="Transactions in last 7 days",
    )
    transactions_30d: int = Field(
        default=0,
        description="Transactions in last 30 days",
    )

    # Amount tracking
    total_amount_30d_cents: int = Field(
        default=0,
        description="Total spend in last 30 days (cents)",
    )

    # Card usage
    distinct_cards_30d: int = Field(
        default=0,
        description="Distinct cards used in last 30 days",
    )
    distinct_cards_lifetime: int = Field(
        default=0,
        description="Distinct cards used (all time)",
    )

    # Historical aggregates
    total_transactions: int = Field(
        default=0,
        description="Total transaction count (all time)",
    )
    total_amount_cents: int = Field(
        default=0,
        description="Total spend (all time, cents)",
    )

    # Chargeback/dispute history (critical for friendly fraud)
    chargeback_count: int = Field(
        default=0,
        description="Total chargebacks",
    )
    chargeback_count_90d: int = Field(
        default=0,
        description="Chargebacks in last 90 days",
    )
    dispute_count: int = Field(
        default=0,
        description="Total disputes filed",
    )
    refund_count_90d: int = Field(
        default=0,
        description="Refunds in last 90 days",
    )

    @property
    def chargeback_rate_90d(self) -> float:
        """Calculate chargeback rate for last 90 days."""
        if self.transactions_30d == 0:
            return 0.0
        # Approximate: use 30d * 3 as denominator
        return self.chargeback_count_90d / max(self.transactions_30d * 3, 1)

    @property
    def is_new_account(self) -> bool:
        """Check if account is less than 7 days old."""
        return self.account_age_days < 7


class MerchantProfile(BaseModel):
    """
    Merchant entity profile.

    Tracks risk metrics for merchants.
    High-risk signals: high chargeback rate, risky MCC,
    unusual transaction patterns.
    """
    merchant_id: str = Field(
        ...,
        description="Merchant identifier",
    )

    # Merchant metadata
    merchant_name: Optional[str] = Field(
        default=None,
        description="Merchant display name",
    )
    mcc: Optional[str] = Field(
        default=None,
        description="Merchant Category Code",
    )
    country: Optional[str] = Field(
        default=None,
        description="Merchant country code",
    )

    # Risk classification
    is_high_risk_mcc: bool = Field(
        default=False,
        description="MCC is in high-risk category",
    )
    risk_tier: str = Field(
        default="NORMAL",
        description="Merchant risk tier: LOW, NORMAL, ELEVATED, HIGH",
    )

    # Volume metrics
    transactions_24h: int = Field(
        default=0,
        description="Transactions in last 24 hours",
    )
    transactions_30d: int = Field(
        default=0,
        description="Transactions in last 30 days",
    )

    # Chargeback tracking
    chargeback_count_30d: int = Field(
        default=0,
        description="Chargebacks in last 30 days",
    )
    chargeback_rate_30d: float = Field(
        default=0.0,
        description="Chargeback rate in last 30 days",
    )

    # Historical aggregates
    total_transactions: int = Field(
        default=0,
        description="Total transaction count (all time)",
    )


class ServiceProfile(BaseModel):
    """
    Service entity profile (telco/MSP).

    Tracks basic service-level activity for subscriber services.
    """
    service_id: str = Field(
        ...,
        description="Service identifier",
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Service display name",
    )
    first_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this service was first seen",
    )
    last_seen: datetime = Field(
        default_factory=_utc_now,
        description="When this service was last seen",
    )
    total_transactions: int = Field(
        default=0,
        description="Total service transactions",
    )


class EntityProfiles(BaseModel):
    """
    Container for all entity profiles associated with a transaction.

    Used to pass enriched entity data through the detection pipeline.
    """
    card: Optional[CardProfile] = Field(
        default=None,
        description="Card profile",
    )
    device: Optional[DeviceProfile] = Field(
        default=None,
        description="Device profile",
    )
    ip: Optional[IPProfile] = Field(
        default=None,
        description="IP profile",
    )
    user: Optional[UserProfile] = Field(
        default=None,
        description="User profile",
    )
    service: Optional[ServiceProfile] = Field(
        default=None,
        description="Service profile",
    )
    merchant: Optional[MerchantProfile] = Field(
        default=None,
        description="Merchant profile",
    )

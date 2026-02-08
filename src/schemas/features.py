"""
Feature Schemas for Telco/MSP Payment Fraud Detection

Defines the feature structures used by the scoring and
detection modules. Features are computed from entity profiles
and real-time velocity counters.

Supports two service verticals:
- Mobile: Phone numbers, IMEIs, SIM cards
- Broadband: Modems, CPE equipment, service addresses
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VelocityFeatures(BaseModel):
    """
    Real-time velocity features computed from sliding window counters.

    These features are critical for detecting active payment fraud attacks
    (card testing, SIM farms, equipment fraud rings).
    """

    # ==========================================================================
    # Card Velocity Features
    # ==========================================================================
    card_attempts_10m: int = Field(
        default=0,
        description="Card transaction attempts in last 10 minutes",
    )
    card_attempts_1h: int = Field(
        default=0,
        description="Card transaction attempts in last 1 hour",
    )
    card_attempts_24h: int = Field(
        default=0,
        description="Card transaction attempts in last 24 hours",
    )
    card_declines_10m: int = Field(
        default=0,
        description="Card declines in last 10 minutes",
    )
    card_declines_1h: int = Field(
        default=0,
        description="Card declines in last 1 hour",
    )
    card_distinct_accounts_24h: int = Field(
        default=0,
        description="Distinct subscriber accounts for card in last 24 hours",
    )
    card_distinct_devices_24h: int = Field(
        default=0,
        description="Distinct devices for card in last 24 hours",
    )
    card_distinct_ips_24h: int = Field(
        default=0,
        description="Distinct IPs for card in last 24 hours",
    )

    # ==========================================================================
    # Mobile-Specific Velocity Features
    # ==========================================================================
    card_distinct_phone_numbers_24h: int = Field(
        default=0,
        description="Distinct phone numbers (MSISDNs) funded by card in 24 hours - SIM farm detection",
    )
    card_distinct_imeis_24h: int = Field(
        default=0,
        description="Distinct device IMEIs purchased/activated with card in 24 hours - device resale fraud",
    )
    imei_distinct_sims_7d: int = Field(
        default=0,
        description="Distinct SIMs activated on same IMEI in 7 days - device cloning detection",
    )
    phone_sim_swaps_30d: int = Field(
        default=0,
        description="SIM swap count for phone number in 30 days - account takeover detection",
    )

    # ==========================================================================
    # Broadband-Specific Velocity Features
    # ==========================================================================
    card_distinct_modems_30d: int = Field(
        default=0,
        description="Distinct modem MACs purchased/activated with card in 30 days - equipment fraud",
    )
    address_distinct_accounts_30d: int = Field(
        default=0,
        description="Distinct accounts at same service address in 30 days - promo stacking",
    )

    # ==========================================================================
    # Device Velocity Features
    # ==========================================================================
    device_attempts_1h: int = Field(
        default=0,
        description="Device transaction attempts in last 1 hour",
    )
    device_attempts_24h: int = Field(
        default=0,
        description="Device transaction attempts in last 24 hours",
    )
    device_distinct_cards_1h: int = Field(
        default=0,
        description="Distinct cards from device in last 1 hour",
    )
    device_distinct_cards_24h: int = Field(
        default=0,
        description="Distinct cards from device in last 24 hours",
    )
    device_distinct_users_24h: int = Field(
        default=0,
        description="Distinct users from device in last 24 hours",
    )

    # ==========================================================================
    # IP Velocity Features
    # ==========================================================================
    ip_attempts_1h: int = Field(
        default=0,
        description="IP transaction attempts in last 1 hour",
    )
    ip_attempts_24h: int = Field(
        default=0,
        description="IP transaction attempts in last 24 hours",
    )
    ip_distinct_cards_1h: int = Field(
        default=0,
        description="Distinct cards from IP in last 1 hour",
    )
    ip_distinct_cards_24h: int = Field(
        default=0,
        description="Distinct cards from IP in last 24 hours",
    )

    # ==========================================================================
    # User/Subscriber Velocity Features
    # ==========================================================================
    user_transactions_24h: int = Field(
        default=0,
        description="User transactions in last 24 hours",
    )
    user_transactions_7d: int = Field(
        default=0,
        description="User transactions in last 7 days",
    )
    user_amount_24h_cents: int = Field(
        default=0,
        description="User total spend in last 24 hours (cents)",
    )
    user_distinct_cards_30d: int = Field(
        default=0,
        description="Distinct cards for user in last 30 days",
    )

    # ==========================================================================
    # Computed Ratios
    # ==========================================================================
    @property
    def card_decline_rate_10m(self) -> float:
        """Card decline rate in 10-minute window."""
        if self.card_attempts_10m == 0:
            return 0.0
        return self.card_declines_10m / self.card_attempts_10m

    @property
    def card_decline_rate_1h(self) -> float:
        """Card decline rate in 1-hour window."""
        if self.card_attempts_1h == 0:
            return 0.0
        return self.card_declines_1h / self.card_attempts_1h


class EntityFeatures(BaseModel):
    """
    Entity-level features derived from historical profiles.

    These features provide context about the entities involved
    in a transaction based on their historical behavior for
    payment fraud detection.
    """

    # ==========================================================================
    # Card Features
    # ==========================================================================
    card_age_days: Optional[int] = Field(
        default=None,
        description="Days since card was first seen",
    )
    card_total_transactions: int = Field(
        default=0,
        description="Total card transactions (all time)",
    )
    card_chargeback_count: int = Field(
        default=0,
        description="Total chargebacks on card",
    )
    card_is_new: bool = Field(
        default=True,
        description="Card seen for the first time",
    )
    last_geo_seen: Optional[datetime] = Field(
        default=None,
        description="Last geo observation timestamp for this card",
    )
    last_geo_lat: Optional[float] = Field(
        default=None,
        description="Last known latitude for this card",
    )
    last_geo_lon: Optional[float] = Field(
        default=None,
        description="Last known longitude for this card",
    )

    # ==========================================================================
    # Device Features
    # ==========================================================================
    device_age_days: Optional[int] = Field(
        default=None,
        description="Days since device was first seen",
    )
    device_is_emulator: bool = Field(
        default=False,
        description="Device appears to be an emulator",
    )
    device_is_rooted: bool = Field(
        default=False,
        description="Device appears to be rooted/jailbroken",
    )
    device_total_transactions: int = Field(
        default=0,
        description="Total device transactions (all time)",
    )
    device_chargeback_count: int = Field(
        default=0,
        description="Total chargebacks from device",
    )

    # ==========================================================================
    # IP Features
    # ==========================================================================
    ip_is_datacenter: bool = Field(
        default=False,
        description="IP is from a datacenter",
    )
    ip_is_vpn: bool = Field(
        default=False,
        description="IP appears to be a VPN",
    )
    ip_is_proxy: bool = Field(
        default=False,
        description="IP appears to be a proxy",
    )
    ip_is_tor: bool = Field(
        default=False,
        description="IP is a Tor exit node",
    )
    ip_country_code: Optional[str] = Field(
        default=None,
        description="IP country code",
    )
    ip_total_transactions: int = Field(
        default=0,
        description="Total IP transactions (all time)",
    )

    # ==========================================================================
    # Service Features (Telco/MSP)
    # ==========================================================================
    service_total_transactions: int = Field(
        default=0,
        description="Total service transactions (all time)",
    )
    service_is_new: bool = Field(
        default=True,
        description="Service seen for the first time",
    )

    # ==========================================================================
    # User/Subscriber Features
    # ==========================================================================
    user_account_age_days: Optional[int] = Field(
        default=None,
        description="Days since account creation",
    )
    user_is_new: bool = Field(
        default=True,
        description="Account is less than 7 days old",
    )
    user_is_guest: bool = Field(
        default=False,
        description="Guest checkout (no account)",
    )
    user_risk_tier: str = Field(
        default="NORMAL",
        description="User risk tier",
    )
    user_total_transactions: int = Field(
        default=0,
        description="Total user transactions (all time)",
    )
    user_chargeback_count: int = Field(
        default=0,
        description="Total user chargebacks",
    )
    user_chargeback_count_90d: int = Field(
        default=0,
        description="User chargebacks in last 90 days",
    )
    user_refund_count_90d: int = Field(
        default=0,
        description="User refunds in last 90 days",
    )

    # ==========================================================================
    # Subscriber Features (Telco-specific)
    # ==========================================================================
    subscriber_age_days: Optional[int] = Field(
        default=None,
        description="Days since subscriber account creation",
    )
    subscriber_is_new: bool = Field(
        default=True,
        description="Subscriber account is less than 30 days old",
    )
    subscriber_total_services: int = Field(
        default=0,
        description="Total active services for subscriber (mobile lines, broadband, etc.)",
    )

    # ==========================================================================
    # Service Features (replaces merchant features)
    # ==========================================================================
    service_is_high_risk: bool = Field(
        default=False,
        description="Service type is high-risk (device upgrade, international enable, equipment purchase)",
    )
    service_chargeback_rate_30d: float = Field(
        default=0.0,
        description="Chargeback rate for this service type in last 30 days",
    )

    # ==========================================================================
    # Cross-Entity Features
    # ==========================================================================
    card_user_match: bool = Field(
        default=True,
        description="Card has been used by this user before",
    )
    device_user_match: bool = Field(
        default=True,
        description="Device has been used by this user before",
    )
    ip_country_card_country_match: bool = Field(
        default=True,
        description="IP country matches card issuing country",
    )


class FeatureSet(BaseModel):
    """
    Complete feature set for a transaction.

    Combines velocity features (real-time) and entity features
    (historical) for use by the scoring and detection modules
    in payment fraud detection.
    """
    velocity: VelocityFeatures = Field(
        default_factory=VelocityFeatures,
        description="Real-time velocity features",
    )
    entity: EntityFeatures = Field(
        default_factory=EntityFeatures,
        description="Entity-level features",
    )

    # Transaction-level features (from the event itself)
    amount_cents: int = Field(
        default=0,
        description="Transaction amount in cents",
    )
    is_high_value: bool = Field(
        default=False,
        description="Transaction exceeds high-value threshold",
    )
    is_recurring: bool = Field(
        default=False,
        description="Recurring/subscription payment",
    )
    has_3ds: bool = Field(
        default=False,
        description="3D Secure was used",
    )
    channel: Optional[str] = Field(
        default=None,
        description="Transaction channel",
    )

    # Service-level features (Telco-specific)
    service_type: Optional[str] = Field(
        default=None,
        description="Service type: mobile or broadband",
    )
    event_subtype: Optional[str] = Field(
        default=None,
        description="Event subtype within service",
    )
    is_high_risk_subtype: bool = Field(
        default=False,
        description="Event subtype is high-risk for payment fraud",
    )

    # Verification features
    avs_match: bool = Field(
        default=True,
        description="AVS check passed",
    )
    cvv_match: bool = Field(
        default=True,
        description="CVV check passed",
    )

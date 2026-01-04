"""
Feature Schemas

Defines the feature structures used by the scoring and
detection modules. Features are computed from entity profiles
and real-time velocity counters.
"""

from typing import Optional

from pydantic import BaseModel, Field


class VelocityFeatures(BaseModel):
    """
    Real-time velocity features computed from sliding window counters.

    These features are critical for detecting active attacks
    (card testing, BIN attacks, fraud rings).
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
    card_distinct_merchants_24h: int = Field(
        default=0,
        description="Distinct merchants for card in last 24 hours",
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
    # User Velocity Features
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
    in a transaction based on their historical behavior.
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
    # User Features
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
    # Merchant Features
    # ==========================================================================
    merchant_is_high_risk_mcc: bool = Field(
        default=False,
        description="Merchant MCC is high-risk",
    )
    merchant_chargeback_rate_30d: float = Field(
        default=0.0,
        description="Merchant chargeback rate in last 30 days",
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
    (historical) for use by the scoring and detection modules.
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

    # Verification features
    avs_match: bool = Field(
        default=True,
        description="AVS check passed",
    )
    cvv_match: bool = Field(
        default=True,
        description="CVV check passed",
    )

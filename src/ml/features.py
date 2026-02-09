"""
ML Feature Extraction

Maps FeatureSet objects and evidence snapshots into a stable
feature vector for model training and inference.
"""

from __future__ import annotations

from typing import Any

from ..schemas import FeatureSet

FEATURE_COLUMNS: list[str] = [
    # Velocity features
    "card_attempts_10m",
    "card_attempts_1h",
    "card_attempts_24h",
    "device_distinct_cards_1h",
    "device_distinct_cards_24h",
    "ip_distinct_cards_1h",
    "user_amount_24h_cents",
    "card_decline_rate_1h",
    # Entity features
    "card_age_hours",
    "device_age_hours",
    "user_account_age_days",
    "user_chargeback_count_lifetime",
    "user_chargeback_rate_90d",
    "user_refund_count_90d",
    "card_distinct_devices_30d",
    "card_distinct_users_30d",
    # Transaction features
    "amount_usd",
    "amount_zscore",
    "is_new_card_for_user",
    "is_new_device_for_user",
    "hour_of_day",
    "is_weekend",
    # Device / network features
    "is_emulator",
    "is_rooted",
    "is_datacenter_ip",
    "is_vpn",
    "is_tor",
    "ip_risk_score",
]


def _as_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_feature_dict(features: FeatureSet) -> dict[str, float]:
    """Extract a normalized feature dict from a FeatureSet."""
    velocity = features.velocity
    entity = features.entity

    values: dict[str, float] = {
        # Velocity
        "card_attempts_10m": velocity.card_attempts_10m,
        "card_attempts_1h": velocity.card_attempts_1h,
        "card_attempts_24h": velocity.card_attempts_24h,
        "device_distinct_cards_1h": velocity.device_distinct_cards_1h,
        "device_distinct_cards_24h": velocity.device_distinct_cards_24h,
        "ip_distinct_cards_1h": velocity.ip_distinct_cards_1h,
        "user_amount_24h_cents": velocity.user_amount_24h_cents,
        "card_decline_rate_1h": velocity.card_decline_rate_1h,
        # Entity
        "card_age_hours": entity.card_age_hours or 0,
        "device_age_hours": entity.device_age_hours or 0,
        "user_account_age_days": entity.user_account_age_days,
        "user_chargeback_count_lifetime": entity.user_chargeback_count,
        "user_chargeback_rate_90d": entity.user_chargeback_rate_90d,
        "user_refund_count_90d": entity.user_refund_count_90d,
        "card_distinct_devices_30d": velocity.card_distinct_devices_30d,
        "card_distinct_users_30d": velocity.card_distinct_users_30d,
        # Transaction
        "amount_usd": features.amount_usd,
        "amount_zscore": features.amount_zscore,
        "is_new_card_for_user": features.is_new_card_for_user,
        "is_new_device_for_user": features.is_new_device_for_user,
        "hour_of_day": features.hour_of_day,
        "is_weekend": features.is_weekend,
        # Device/network
        "is_emulator": entity.device_is_emulator,
        "is_rooted": entity.device_is_rooted,
        "is_datacenter_ip": entity.ip_is_datacenter,
        "is_vpn": entity.ip_is_vpn,
        "is_tor": entity.ip_is_tor,
        "ip_risk_score": entity.ip_risk_score,
    }

    return {key: _as_number(value) for key, value in values.items()}


def vector_from_feature_dict(values: dict[str, float]) -> list[float]:
    """Return a feature vector ordered by FEATURE_COLUMNS."""
    return [float(values.get(name, 0.0)) for name in FEATURE_COLUMNS]


def extract_from_snapshot(snapshot: dict[str, Any]) -> dict[str, float]:
    """
    Extract features from an evidence snapshot.

    Expected snapshot format:
    {
      "velocity": {...},
      "entity": {...},
      "transaction": {...}
    }
    """
    velocity = snapshot.get("velocity") or {}
    entity = snapshot.get("entity") or {}
    transaction = snapshot.get("transaction") or {}

    decline_rate_1h = velocity.get("card_decline_rate_1h")
    if decline_rate_1h is None:
        attempts_1h = _as_number(velocity.get("card_attempts_1h"))
        declines_1h = _as_number(velocity.get("card_declines_1h"))
        decline_rate_1h = declines_1h / attempts_1h if attempts_1h > 0 else 0.0

    values: dict[str, float] = {
        "card_attempts_10m": velocity.get("card_attempts_10m"),
        "card_attempts_1h": velocity.get("card_attempts_1h"),
        "card_attempts_24h": velocity.get("card_attempts_24h"),
        "device_distinct_cards_1h": velocity.get("device_distinct_cards_1h"),
        "device_distinct_cards_24h": velocity.get("device_distinct_cards_24h"),
        "ip_distinct_cards_1h": velocity.get("ip_distinct_cards_1h"),
        "user_amount_24h_cents": velocity.get("user_amount_24h_cents"),
        "card_decline_rate_1h": decline_rate_1h,
        "card_age_hours": entity.get("card_age_hours"),
        "device_age_hours": entity.get("device_age_hours"),
        "user_account_age_days": entity.get("user_account_age_days"),
        "user_chargeback_count_lifetime": entity.get("user_chargeback_count"),
        "user_chargeback_rate_90d": entity.get("user_chargeback_rate_90d"),
        "user_refund_count_90d": entity.get("user_refund_count_90d"),
        "card_distinct_devices_30d": velocity.get("card_distinct_devices_30d"),
        "card_distinct_users_30d": velocity.get("card_distinct_users_30d"),
        "amount_usd": transaction.get("amount_usd"),
        "amount_zscore": transaction.get("amount_zscore"),
        "is_new_card_for_user": transaction.get("is_new_card_for_user"),
        "is_new_device_for_user": transaction.get("is_new_device_for_user"),
        "hour_of_day": transaction.get("hour_of_day"),
        "is_weekend": transaction.get("is_weekend"),
        "is_emulator": entity.get("device_is_emulator"),
        "is_rooted": entity.get("device_is_rooted"),
        "is_datacenter_ip": entity.get("ip_is_datacenter"),
        "is_vpn": entity.get("ip_is_vpn"),
        "is_tor": entity.get("ip_is_tor"),
        "ip_risk_score": entity.get("ip_risk_score"),
    }

    return {key: _as_number(value) for key, value in values.items()}

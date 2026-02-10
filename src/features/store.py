"""
Feature Store

Central service for computing and retrieving features for
fraud detection. Combines:
- Real-time velocity features (from Redis ZSETs)
- Entity profile features (from Redis Hashes)
- Transaction-level features (from the event itself)

Design goals:
- <50ms total feature computation time
- Parallel Redis operations where possible
- Graceful degradation on Redis failure
"""

import asyncio
import time
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any, Optional

import redis.asyncio as redis

from ..config import settings
from ..schemas import (
    PaymentEvent,
    CardProfile,
    DeviceProfile,
    IPProfile,
    UserProfile,
    ServiceProfile,
    MerchantProfile,
    EntityProfiles,
    VelocityFeatures,
    EntityFeatures,
    FeatureSet,
)
from .velocity import VelocityCounter


class FeatureStore:
    """
    Feature computation and storage service.

    Provides:
    - Real-time velocity features via sliding window counters
    - Entity profiles from Redis hashes
    - Feature enrichment for incoming transactions
    """

    # Window sizes in seconds
    WINDOW_10M = 600
    WINDOW_1H = 3600
    WINDOW_24H = 86400
    WINDOW_7D = 604800
    WINDOW_30D = 2592000
    WINDOW_90D = 7776000

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize feature store.

        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self.prefix = settings.redis_key_prefix
        self.velocity = VelocityCounter(redis_client, self.prefix)

    # =========================================================================
    # Velocity Feature Computation
    # =========================================================================

    async def compute_velocity_features(
        self,
        event: PaymentEvent,
    ) -> VelocityFeatures:
        """
        Compute real-time velocity features for a transaction.

        Executes multiple Redis queries in parallel for efficiency.

        Args:
            event: Payment event

        Returns:
            VelocityFeatures with all velocity metrics
        """
        # Prepare parallel queries
        tasks = []

        # Card velocity features
        if event.card_token:
            tasks.extend([
                self._get_card_velocity(event.card_token),
            ])

        # Device velocity features
        if event.device_id:
            tasks.extend([
                self._get_device_velocity(event.device_id),
            ])

        # IP velocity features
        if event.ip_address:
            tasks.extend([
                self._get_ip_velocity(event.ip_address),
            ])

        # User velocity features
        if event.user_id:
            tasks.extend([
                self._get_user_velocity(event.user_id),
            ])

        # Execute all queries in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results into VelocityFeatures
        features = VelocityFeatures()

        # Process results (handle failures gracefully)
        for result in results:
            if isinstance(result, Exception):
                # Log error but continue with default values
                continue
            if isinstance(result, dict):
                # Update features with result
                for key, value in result.items():
                    if hasattr(features, key):
                        setattr(features, key, value)

        return features

    async def _get_card_velocity(self, card_token: str) -> dict:
        """Get velocity features for a card."""
        counts: dict[str, int] = {}

        # Get all card velocity metrics in parallel
        results = await asyncio.gather(
            self.velocity.count("card", card_token, "attempts", self.WINDOW_10M),
            self.velocity.count("card", card_token, "attempts", self.WINDOW_1H),
            self.velocity.count("card", card_token, "attempts", self.WINDOW_24H),
            self.velocity.count("card", card_token, "declines", self.WINDOW_10M),
            self.velocity.count("card", card_token, "declines", self.WINDOW_1H),
            self.velocity.count_distinct("card", card_token, "accounts", self.WINDOW_24H),
            self.velocity.count_distinct("card", card_token, "devices", self.WINDOW_24H),
            self.velocity.count_distinct("card", card_token, "devices", self.WINDOW_30D),
            self.velocity.count_distinct("card", card_token, "ips", self.WINDOW_24H),
            self.velocity.count_distinct("card", card_token, "users", self.WINDOW_30D),
        )

        return {
            "card_attempts_10m": results[0],
            "card_attempts_1h": results[1],
            "card_attempts_24h": results[2],
            "card_declines_10m": results[3],
            "card_declines_1h": results[4],
            "card_distinct_accounts_24h": results[5],
            "card_distinct_devices_24h": results[6],
            "card_distinct_devices_30d": results[7],
            "card_distinct_ips_24h": results[8],
            "card_distinct_users_30d": results[9],
        }

    async def _get_device_velocity(self, device_id: str) -> dict:
        """Get velocity features for a device."""
        results = await asyncio.gather(
            self.velocity.count("device", device_id, "attempts", self.WINDOW_1H),
            self.velocity.count("device", device_id, "attempts", self.WINDOW_24H),
            self.velocity.count_distinct("device", device_id, "cards", self.WINDOW_1H),
            self.velocity.count_distinct("device", device_id, "cards", self.WINDOW_24H),
            self.velocity.count_distinct("device", device_id, "users", self.WINDOW_24H),
        )

        return {
            "device_attempts_1h": results[0],
            "device_attempts_24h": results[1],
            "device_distinct_cards_1h": results[2],
            "device_distinct_cards_24h": results[3],
            "device_distinct_users_24h": results[4],
        }

    async def _get_ip_velocity(self, ip_address: str) -> dict:
        """Get velocity features for an IP address."""
        results = await asyncio.gather(
            self.velocity.count("ip", ip_address, "attempts", self.WINDOW_1H),
            self.velocity.count("ip", ip_address, "attempts", self.WINDOW_24H),
            self.velocity.count_distinct("ip", ip_address, "cards", self.WINDOW_1H),
            self.velocity.count_distinct("ip", ip_address, "cards", self.WINDOW_24H),
        )

        return {
            "ip_attempts_1h": results[0],
            "ip_attempts_24h": results[1],
            "ip_distinct_cards_1h": results[2],
            "ip_distinct_cards_24h": results[3],
        }

    async def _get_user_velocity(self, user_id: str) -> dict:
        """Get velocity features for a user."""
        results = await asyncio.gather(
            self.velocity.count("user", user_id, "transactions", self.WINDOW_24H),
            self.velocity.count("user", user_id, "transactions", self.WINDOW_7D),
            self.velocity.count_distinct("user", user_id, "cards", self.WINDOW_30D),
        )

        # Also get amount (stored separately as a simple key)
        amount_key = f"{self.prefix}user:{user_id}:amount_24h"
        amount = await self.redis.get(amount_key)

        return {
            "user_transactions_24h": results[0],
            "user_transactions_7d": results[1],
            "user_distinct_cards_30d": results[2],
            "user_amount_24h_cents": int(amount) if amount else 0,
        }

    # =========================================================================
    # Entity Profile Operations
    # =========================================================================

    async def get_entity_profiles(
        self,
        event: PaymentEvent,
    ) -> EntityProfiles:
        """
        Retrieve entity profiles for a transaction.

        Args:
            event: Payment event

        Returns:
            EntityProfiles with all available profiles
        """
        tasks: list[Any] = []
        keys: list[str] = []

        # Queue profile lookups
        if event.card_token:
            tasks.append(self._get_card_profile(event.card_token))
            keys.append("card")

        if event.device_id:
            tasks.append(self._get_device_profile(event.device_id))
            keys.append("device")

        if event.ip_address:
            tasks.append(self._get_ip_profile(event.ip_address))
            keys.append("ip")

        if event.user_id:
            tasks.append(self._get_user_profile(event.user_id))
            keys.append("user")

        # Service profile (replaces merchant profile for telco)
        if event.service_id:
            tasks.append(self._get_service_profile(event.service_id))
            keys.append("service")

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build profiles object
        profiles = EntityProfiles()
        for key, result in zip(keys, results):
            if not isinstance(result, Exception) and result is not None:
                setattr(profiles, key, result)

        return profiles

    async def _get_card_profile(self, card_token: str) -> Optional[CardProfile]:
        """Get card profile from Redis hash."""
        key = f"{self.prefix}profile:card:{card_token}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return CardProfile(
            card_token=card_token,
            first_seen=datetime.fromisoformat(data.get("first_seen", datetime.now(UTC).isoformat())),
            last_seen=datetime.fromisoformat(data.get("last_seen", datetime.now(UTC).isoformat())),
            last_geo_seen=datetime.fromisoformat(data["last_geo_seen"]) if data.get("last_geo_seen") else None,
            last_geo_lat=float(data["last_geo_lat"]) if data.get("last_geo_lat") else None,
            last_geo_lon=float(data["last_geo_lon"]) if data.get("last_geo_lon") else None,
            total_transactions=int(data.get("total_transactions", 0)),
            chargeback_count=int(data.get("chargeback_count", 0)),
        )

    async def _get_device_profile(self, device_id: str) -> Optional[DeviceProfile]:
        """Get device profile from Redis hash."""
        key = f"{self.prefix}profile:device:{device_id}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return DeviceProfile(
            device_id=device_id,
            first_seen=datetime.fromisoformat(data.get("first_seen", datetime.now(UTC).isoformat())),
            last_seen=datetime.fromisoformat(data.get("last_seen", datetime.now(UTC).isoformat())),
            is_emulator=data.get("is_emulator", "false").lower() == "true",
            is_rooted=data.get("is_rooted", "false").lower() == "true",
            total_transactions=int(data.get("total_transactions", 0)),
            chargeback_count=int(data.get("chargeback_count", 0)),
            last_country=data.get("last_country"),
            last_city=data.get("last_city"),
        )

    async def _get_ip_profile(self, ip_address: str) -> Optional[IPProfile]:
        """Get IP profile from Redis hash."""
        key = f"{self.prefix}profile:ip:{ip_address}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return IPProfile(
            ip_address=ip_address,
            first_seen=datetime.fromisoformat(data.get("first_seen", datetime.now(UTC).isoformat())),
            last_seen=datetime.fromisoformat(data.get("last_seen", datetime.now(UTC).isoformat())),
            is_datacenter=data.get("is_datacenter", "false").lower() == "true",
            is_vpn=data.get("is_vpn", "false").lower() == "true",
            is_proxy=data.get("is_proxy", "false").lower() == "true",
            is_tor=data.get("is_tor", "false").lower() == "true",
            country_code=data.get("country_code"),
            region=data.get("region"),
            city=data.get("city"),
            total_transactions=int(data.get("total_transactions", 0)),
            chargeback_count=int(data.get("chargeback_count", 0)),
        )

    async def _get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile from Redis hash."""
        key = f"{self.prefix}profile:user:{user_id}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return UserProfile(
            user_id=user_id,
            account_age_days=int(data.get("account_age_days", 0)),
            risk_tier=data.get("risk_tier", "NORMAL"),
            total_transactions=int(data.get("total_transactions", 0)),
            transactions_30d=int(data.get("transactions_30d", data.get("total_transactions", 0))),
            total_amount_cents=int(data.get("total_amount_cents", 0)),
            chargeback_count=int(data.get("chargeback_count", 0)),
            chargeback_count_90d=int(data.get("chargeback_count_90d", 0)),
            refund_count_90d=int(data.get("refund_count_90d", 0)),
            amount_mean_cents=float(data.get("amount_mean_cents", 0.0)),
            amount_m2_cents=float(data.get("amount_m2_cents", 0.0)),
            amount_count=int(data.get("amount_count", 0)),
        )

    async def _get_service_profile(self, service_id: str) -> Optional[ServiceProfile]:
        """Get service profile from Redis hash."""
        key = f"{self.prefix}profile:service:{service_id}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return ServiceProfile(
            service_id=service_id,
            service_name=data.get("service_name"),
            first_seen=datetime.fromisoformat(data.get("first_seen", datetime.now(UTC).isoformat())),
            last_seen=datetime.fromisoformat(data.get("last_seen", datetime.now(UTC).isoformat())),
            total_transactions=int(data.get("total_transactions", 0)),
        )

    async def _get_merchant_profile(self, merchant_id: str) -> Optional[MerchantProfile]:
        """Get merchant profile from Redis hash."""
        key = f"{self.prefix}profile:merchant:{merchant_id}"
        data = await self.redis.hgetall(key)  # type: ignore[misc]

        if not data:
            return None

        return MerchantProfile(
            merchant_id=merchant_id,
            merchant_name=data.get("merchant_name"),
            mcc=data.get("mcc"),
            country=data.get("country"),
            is_high_risk_mcc=data.get("is_high_risk_mcc", "false").lower() == "true",
            risk_tier=data.get("risk_tier", "NORMAL"),
            chargeback_rate_30d=float(data.get("chargeback_rate_30d", 0)),
            total_transactions=int(data.get("total_transactions", 0)),
        )

    # =========================================================================
    # Entity Profile Updates
    # =========================================================================

    async def update_entity_profiles(
        self,
        event: PaymentEvent,
        is_decline: bool = False,
    ) -> None:
        """
        Update entity profiles after a transaction.

        Called after decision is made to update:
        - Velocity counters
        - Entity profiles
        - Distinct entity tracking

        Args:
            event: Payment event
            is_decline: Whether the transaction was declined
        """
        now = datetime.now(UTC)
        now_ms = int(time.time() * 1000)
        tasks = []

        # Update card profile and velocity
        if event.card_token:
            tasks.append(self._update_card(event, now, now_ms, is_decline))

        # Update device profile and velocity
        if event.device_id:
            tasks.append(self._update_device(event, now, now_ms))

        # Update IP profile and velocity
        if event.ip_address:
            tasks.append(self._update_ip(event, now, now_ms))

        # Update user profile and velocity
        if event.user_id:
            tasks.append(self._update_user(event, now, now_ms))

        # Update service profile (telco/MSP)
        if event.service_id:
            tasks.append(self._update_service(event, now, now_ms))

        # Execute all updates in parallel
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_card(
        self,
        event: PaymentEvent,
        now: datetime,
        now_ms: int,
        is_decline: bool,
    ) -> None:
        """Update card profile and velocity counters."""
        card_token = event.card_token
        tx_id = event.transaction_id

        pipe = self.redis.pipeline()

        # Update velocity counters
        await self.velocity.increment(
            "card", card_token, "attempts", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
        )

        if is_decline:
            await self.velocity.increment(
                "card", card_token, "declines", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
            )

        # Track distinct entities (service_id replaces merchant_id for telco)
        if event.service_id:
            await self.velocity.add_distinct(
                "card", card_token, "accounts", event.service_id, now_ms, ttl_seconds=self.WINDOW_30D
            )
        if event.device and event.device.device_id:
            await self.velocity.add_distinct(
                "card", card_token, "devices", event.device.device_id, now_ms, ttl_seconds=self.WINDOW_30D
            )
        if event.geo and event.geo.ip_address:
            await self.velocity.add_distinct(
                "card", card_token, "ips", event.geo.ip_address, now_ms, ttl_seconds=self.WINDOW_30D
            )
        if event.user_id:
            await self.velocity.add_distinct(
                "card", card_token, "users", event.user_id, now_ms, ttl_seconds=self.WINDOW_30D
            )

        # Update profile hash
        profile_key = f"{self.prefix}profile:card:{card_token}"
        pipe.hsetnx(profile_key, "first_seen", now.isoformat())
        pipe.hset(profile_key, "last_seen", now.isoformat())
        pipe.hincrby(profile_key, "total_transactions", 1)
        pipe.expire(profile_key, self.WINDOW_90D)

        if event.geo and event.geo.latitude is not None and event.geo.longitude is not None:
            pipe.hset(profile_key, "last_geo_seen", now.isoformat())
            pipe.hset(profile_key, "last_geo_lat", str(event.geo.latitude))
            pipe.hset(profile_key, "last_geo_lon", str(event.geo.longitude))

        await pipe.execute()

    async def _update_device(
        self,
        event: PaymentEvent,
        now: datetime,
        now_ms: int,
    ) -> None:
        """Update device profile and velocity counters."""
        assert event.device_id is not None
        device_id: str = event.device_id
        tx_id = event.transaction_id

        pipe = self.redis.pipeline()

        # Update velocity counters
        await self.velocity.increment(
            "device", device_id, "attempts", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
        )

        # Track distinct cards and users
        await self.velocity.add_distinct(
            "device", device_id, "cards", event.card_token, now_ms, ttl_seconds=self.WINDOW_30D
        )
        if event.user_id:
            await self.velocity.add_distinct(
                "device", device_id, "users", event.user_id, now_ms, ttl_seconds=self.WINDOW_30D
            )

        # Update profile hash
        profile_key = f"{self.prefix}profile:device:{device_id}"
        pipe.hsetnx(profile_key, "first_seen", now.isoformat())
        pipe.hset(profile_key, "last_seen", now.isoformat())
        pipe.hincrby(profile_key, "total_transactions", 1)

        if event.device:
            pipe.hset(profile_key, "is_emulator", str(event.device.is_emulator).lower())
            pipe.hset(profile_key, "is_rooted", str(event.device.is_rooted).lower())

        if event.geo:
            pipe.hset(profile_key, "last_country", event.geo.country_code or "")
            pipe.hset(profile_key, "last_city", event.geo.city or "")

        pipe.expire(profile_key, self.WINDOW_90D)
        await pipe.execute()

    async def _update_ip(
        self,
        event: PaymentEvent,
        now: datetime,
        now_ms: int,
    ) -> None:
        """Update IP profile and velocity counters."""
        assert event.ip_address is not None
        ip_address: str = event.ip_address
        tx_id = event.transaction_id

        pipe = self.redis.pipeline()

        # Update velocity counters
        await self.velocity.increment(
            "ip", ip_address, "attempts", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
        )

        # Track distinct cards
        await self.velocity.add_distinct(
            "ip", ip_address, "cards", event.card_token, now_ms, ttl_seconds=self.WINDOW_30D
        )

        # Update profile hash
        profile_key = f"{self.prefix}profile:ip:{ip_address}"
        pipe.hsetnx(profile_key, "first_seen", now.isoformat())
        pipe.hset(profile_key, "last_seen", now.isoformat())
        pipe.hincrby(profile_key, "total_transactions", 1)

        if event.geo:
            pipe.hset(profile_key, "is_datacenter", str(event.geo.is_datacenter).lower())
            pipe.hset(profile_key, "is_vpn", str(event.geo.is_vpn).lower())
            pipe.hset(profile_key, "is_proxy", str(event.geo.is_proxy).lower())
            pipe.hset(profile_key, "is_tor", str(event.geo.is_tor).lower())
            pipe.hset(profile_key, "country_code", event.geo.country_code or "")
            pipe.hset(profile_key, "region", event.geo.region or "")
            pipe.hset(profile_key, "city", event.geo.city or "")

        pipe.expire(profile_key, self.WINDOW_30D)
        await pipe.execute()

    async def _update_user(
        self,
        event: PaymentEvent,
        now: datetime,
        now_ms: int,
    ) -> None:
        """Update user profile and velocity counters."""
        assert event.user_id is not None
        user_id: str = event.user_id
        tx_id = event.transaction_id

        pipe = self.redis.pipeline()

        # Update velocity counters
        await self.velocity.increment(
            "user", user_id, "transactions", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
        )

        # Track distinct cards
        await self.velocity.add_distinct(
            "user", user_id, "cards", event.card_token, now_ms, ttl_seconds=self.WINDOW_30D
        )
        if event.device_id:
            await self.velocity.add_distinct(
                "user", user_id, "devices", event.device_id, now_ms, ttl_seconds=self.WINDOW_30D
            )

        # Update amount counter
        amount_key = f"{self.prefix}user:{user_id}:amount_24h"
        pipe.incrby(amount_key, event.amount_cents)
        pipe.expire(amount_key, self.WINDOW_24H)

        # Update profile hash
        profile_key = f"{self.prefix}profile:user:{user_id}"
        amount_count, amount_mean, amount_m2 = await self._update_amount_stats(
            profile_key, event.amount_cents
        )
        pipe.hsetnx(profile_key, "first_transaction", now.isoformat())
        pipe.hset(profile_key, "last_transaction", now.isoformat())
        pipe.hincrby(profile_key, "total_transactions", 1)
        pipe.hincrby(profile_key, "transactions_30d", 1)
        pipe.hincrby(profile_key, "total_amount_cents", event.amount_cents)
        pipe.hset(profile_key, "amount_count", str(amount_count))
        pipe.hset(profile_key, "amount_mean_cents", str(amount_mean))
        pipe.hset(profile_key, "amount_m2_cents", str(amount_m2))

        if event.account_age_days is not None:
            pipe.hset(profile_key, "account_age_days", str(event.account_age_days))

        pipe.expire(profile_key, self.WINDOW_30D)
        await pipe.execute()

    async def _update_amount_stats(
        self,
        profile_key: str,
        amount_cents: int,
    ) -> tuple[int, float, float]:
        """
        Update running mean/variance (Welford) for transaction amounts.

        Returns updated (count, mean, m2).
        """
        existing = await self.redis.hmget(  # type: ignore[misc]
            profile_key,
            "amount_count",
            "amount_mean_cents",
            "amount_m2_cents",
        )

        def _to_float(value: Optional[bytes]) -> float:
            if value is None:
                return 0.0
            if isinstance(value, bytes):
                return float(value.decode("utf-8"))
            return float(value)

        count = int(_to_float(existing[0]) if existing[0] is not None else 0)
        mean = _to_float(existing[1])
        m2 = _to_float(existing[2])

        count += 1
        delta = amount_cents - mean
        mean += delta / count
        delta2 = amount_cents - mean
        m2 += delta * delta2

        return count, round(mean, 4), round(m2, 4)

    async def _update_service(
        self,
        event: PaymentEvent,
        now: datetime,
        now_ms: int,
    ) -> None:
        """Update service profile counters."""
        service_id = event.service_id
        tx_id = event.transaction_id

        pipe = self.redis.pipeline()

        # Track velocity for service (basic)
        await self.velocity.increment(
            "service", service_id, "transactions", tx_id, now_ms, ttl_seconds=self.WINDOW_30D
        )

        profile_key = f"{self.prefix}profile:service:{service_id}"
        pipe.hsetnx(profile_key, "first_seen", now.isoformat())
        pipe.hset(profile_key, "last_seen", now.isoformat())
        pipe.hincrby(profile_key, "total_transactions", 1)
        if event.service_name:
            pipe.hset(profile_key, "service_name", event.service_name)

        pipe.expire(profile_key, self.WINDOW_30D)
        await pipe.execute()

    # =========================================================================
    # Chargeback Profile Updates
    # =========================================================================

    async def update_chargeback_profiles(
        self,
        card_token: Optional[str] = None,
        user_id: Optional[str] = None,
        device_id_hash: Optional[str] = None,
        ip_address_hash: Optional[str] = None,
    ) -> None:
        """
        Increment chargeback counters on entity profiles.

        Called when a chargeback notification is ingested. Only card and user
        profiles are updated because the evidence vault stores hashed device/IP
        identifiers that cannot be mapped back to the raw keys used in Redis.
        """
        pipe = self.redis.pipeline()
        if card_token:
            key = f"{self.prefix}profile:card:{card_token}"
            pipe.hincrby(key, "chargeback_count", 1)
            pipe.expire(key, self.WINDOW_90D)
        if user_id:
            key = f"{self.prefix}profile:user:{user_id}"
            pipe.hincrby(key, "chargeback_count", 1)
            pipe.hincrby(key, "chargeback_count_90d", 1)
            pipe.expire(key, self.WINDOW_90D)
        await pipe.execute()

    # =========================================================================
    # Refund Profile Updates
    # =========================================================================

    async def update_refund_profiles(
        self,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Increment refund counters on entity profiles.

        Called when a refund notification is ingested. Only user
        profiles are updated because refunds are tied to account-level
        behavior for friendly fraud detection in this MVP.
        """
        if not user_id:
            return
        pipe = self.redis.pipeline()
        key = f"{self.prefix}profile:user:{user_id}"
        pipe.hincrby(key, "refund_count_90d", 1)
        pipe.expire(key, self.WINDOW_90D)
        await pipe.execute()

    # =========================================================================
    # Full Feature Computation
    # =========================================================================

    async def compute_features(
        self,
        event: PaymentEvent,
    ) -> FeatureSet:
        """
        Compute complete feature set for a transaction.

        Combines:
        - Velocity features (real-time counters)
        - Entity features (from profiles)
        - Transaction features (from the event)

        Args:
            event: Payment event

        Returns:
            Complete FeatureSet
        """
        # Compute velocity, profiles, and relationship flags in parallel
        velocity_task = self.compute_velocity_features(event)
        profiles_task = self.get_entity_profiles(event)
        relation_task = self._get_relationship_flags(event)

        velocity_features, profiles, relation_flags = await asyncio.gather(
            velocity_task, profiles_task, relation_task
        )

        # Build entity features from profiles
        entity_features = self._build_entity_features(event, profiles)
        if relation_flags:
            entity_features.card_user_match = relation_flags.get("card_user_match", True)
            entity_features.device_user_match = relation_flags.get("device_user_match", True)

        # Build complete feature set
        amount_zscore = self._compute_amount_zscore(event, profiles, velocity_features)
        hour_of_day, is_weekend = self._derive_time_features(event)
        is_new_card_for_user = not entity_features.card_user_match
        is_new_device_for_user = not entity_features.device_user_match

        return FeatureSet(
            velocity=velocity_features,
            entity=entity_features,
            amount_cents=event.amount_cents,
            amount_usd=round(event.amount_cents / 100, 2) if event.amount_cents else 0.0,
            amount_zscore=amount_zscore,
            is_high_value=event.is_high_value,
            is_recurring=event.is_recurring,
            has_3ds=event.has_3ds,
            channel=event.channel,
            hour_of_day=hour_of_day,
            is_weekend=is_weekend,
            is_new_card_for_user=is_new_card_for_user,
            is_new_device_for_user=is_new_device_for_user,
            avs_match=self._check_avs(event),
            cvv_match=self._check_cvv(event),
        )

    async def _get_relationship_flags(self, event: PaymentEvent) -> dict[str, bool]:
        """Determine whether the user has seen the card/device recently."""
        flags: dict[str, bool] = {}
        if event.user_id and event.card_token:
            flags["card_user_match"] = await self.velocity.has_distinct(
                "card", event.card_token, "users", event.user_id, window_seconds=self.WINDOW_30D
            )
        if event.user_id and event.device_id:
            flags["device_user_match"] = await self.velocity.has_distinct(
                "device", event.device_id, "users", event.user_id, window_seconds=self.WINDOW_30D
            )
        return flags

    @staticmethod
    def _derive_time_features(event: PaymentEvent) -> tuple[int, bool]:
        """Derive hour-of-day and weekend flags from event timestamp."""
        ts = event.timestamp
        if event.device and event.device.timezone:
            try:
                ts = ts.astimezone(ZoneInfo(event.device.timezone))
            except ZoneInfoNotFoundError:
                pass
        hour = ts.hour
        is_weekend = ts.weekday() >= 5
        return hour, is_weekend

    @staticmethod
    def _compute_amount_zscore(
        event: PaymentEvent,
        profiles: EntityProfiles,
        velocity: VelocityFeatures,
    ) -> float:
        """
        Compute an approximate amount z-score against user history.

        Uses running mean/variance when available; otherwise falls back to
        24h average with a conservative standard deviation.
        """
        amount = float(event.amount_cents or 0)
        mean = None
        std = None

        if profiles.user and profiles.user.amount_count >= 2:
            mean = profiles.user.amount_mean_cents
            variance = profiles.user.amount_m2_cents / max(profiles.user.amount_count - 1, 1)
            std = variance ** 0.5

        if mean is None or std is None or std <= 0:
            avg_24h = 0.0
            if velocity.user_transactions_24h > 0:
                avg_24h = velocity.user_amount_24h_cents / velocity.user_transactions_24h
            mean = avg_24h
            std = max(avg_24h, 1.0)

        return round((amount - mean) / std, 4)

    def _build_entity_features(
        self,
        event: PaymentEvent,
        profiles: EntityProfiles,
    ) -> EntityFeatures:
        """Build entity features from profiles."""
        features = EntityFeatures()

        # Card features
        if profiles.card:
            card = profiles.card
            features.card_age_days = (datetime.now(UTC) - card.first_seen).days
            features.card_age_hours = int((datetime.now(UTC) - card.first_seen).total_seconds() / 3600)
            features.card_total_transactions = card.total_transactions
            features.card_chargeback_count = card.chargeback_count
            features.card_is_new = card.total_transactions == 0
            features.last_geo_seen = card.last_geo_seen
            features.last_geo_lat = card.last_geo_lat
            features.last_geo_lon = card.last_geo_lon
        else:
            features.card_is_new = True

        # Device features
        if profiles.device:
            device = profiles.device
            features.device_age_days = (datetime.now(UTC) - device.first_seen).days
            features.device_age_hours = int((datetime.now(UTC) - device.first_seen).total_seconds() / 3600)
            features.device_is_emulator = device.is_emulator
            features.device_is_rooted = device.is_rooted
            features.device_total_transactions = device.total_transactions
            features.device_chargeback_count = device.chargeback_count
        elif event.device:
            features.device_is_emulator = event.device.is_emulator
            features.device_is_rooted = event.device.is_rooted

        # IP features
        if profiles.ip:
            ip = profiles.ip
            features.ip_is_datacenter = ip.is_datacenter
            features.ip_is_vpn = ip.is_vpn
            features.ip_is_proxy = ip.is_proxy
            features.ip_is_tor = ip.is_tor
            features.ip_country_code = ip.country_code
            features.ip_total_transactions = ip.total_transactions
            features.ip_risk_score = self._derive_ip_risk_score(ip.is_datacenter, ip.is_vpn, ip.is_tor, ip.is_proxy)
        elif event.geo:
            features.ip_is_datacenter = event.geo.is_datacenter
            features.ip_is_vpn = event.geo.is_vpn
            features.ip_is_proxy = event.geo.is_proxy
            features.ip_is_tor = event.geo.is_tor
            features.ip_country_code = event.geo.country_code
            features.ip_risk_score = self._derive_ip_risk_score(
                event.geo.is_datacenter, event.geo.is_vpn, event.geo.is_tor, event.geo.is_proxy
            )

        # User features
        if profiles.user:
            user = profiles.user
            features.user_account_age_days = user.account_age_days
            features.user_is_new = user.account_age_days < 7
            features.user_risk_tier = user.risk_tier
            features.user_total_transactions = user.total_transactions
            features.user_chargeback_count = user.chargeback_count
            features.user_chargeback_count_90d = user.chargeback_count_90d
            features.user_refund_count_90d = user.refund_count_90d
            features.user_chargeback_rate_90d = user.chargeback_rate_90d
        else:
            features.user_is_new = True
            features.user_is_guest = event.is_guest

        # Merchant features
        if profiles.merchant:
            features.merchant_is_high_risk_mcc = profiles.merchant.is_high_risk_mcc
            features.merchant_chargeback_rate_30d = profiles.merchant.chargeback_rate_30d

        # Service features (telco/MSP)
        if profiles.service:
            features.service_total_transactions = profiles.service.total_transactions
            features.service_is_new = profiles.service.total_transactions == 0

        # Cross-entity features
        features.ip_country_card_country_match = self._check_country_match(event, profiles)

        return features

    @staticmethod
    def _derive_ip_risk_score(
        is_datacenter: bool,
        is_vpn: bool,
        is_tor: bool,
        is_proxy: bool,
    ) -> float:
        """Derive a simple IP risk score from network flags."""
        score = 0.0
        if is_datacenter:
            score += 0.5
        if is_vpn:
            score += 0.3
        if is_proxy:
            score += 0.2
        if is_tor:
            score += 0.7
        return min(score, 1.0)

    def _check_avs(self, event: PaymentEvent) -> bool:
        """Check if AVS verification passed."""
        if not event.verification or not event.verification.avs_result:
            return True  # No AVS = assume pass
        # Common AVS pass codes
        return event.verification.avs_result in ["Y", "M", "X", "D", "F"]

    def _check_cvv(self, event: PaymentEvent) -> bool:
        """Check if CVV verification passed."""
        if not event.verification or not event.verification.cvv_result:
            return True  # No CVV = assume pass
        return event.verification.cvv_result == "M"

    def _check_country_match(
        self,
        event: PaymentEvent,
        profiles: EntityProfiles,
    ) -> bool:
        """Check if IP country matches card country."""
        ip_country = None
        card_country = event.card_country

        if profiles.ip and profiles.ip.country_code:
            ip_country = profiles.ip.country_code
        elif event.geo and event.geo.country_code:
            ip_country = event.geo.country_code

        if not ip_country or not card_country:
            return True  # Can't verify = assume match

        return ip_country.upper() == card_country.upper()

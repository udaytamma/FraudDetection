"""
Velocity Counter Implementation

Uses Redis Sorted Sets (ZSETs) for sliding window counters.
ZSETs allow efficient:
- Adding events with timestamps as scores
- Counting events within a time window
- Cleaning up expired events

Key format: {prefix}{entity_type}:{entity_id}:{metric}
Example: fraud:card:tok_abc123:attempts
"""

import time
from typing import Optional

import redis.asyncio as redis


class VelocityCounter:
    """
    Sliding window velocity counter using Redis ZSETs.

    Each counter is a ZSET where:
    - Members are unique event identifiers (transaction_id)
    - Scores are Unix timestamps (milliseconds)

    This allows efficient counting of events within any time window.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "fraud:",
        default_ttl_seconds: int = 86400,  # 24 hours
    ):
        """
        Initialize velocity counter.

        Args:
            redis_client: Async Redis client
            key_prefix: Prefix for all Redis keys
            default_ttl_seconds: Default TTL for keys (24 hours)
        """
        self.redis = redis_client
        self.prefix = key_prefix
        self.default_ttl = default_ttl_seconds

    def _make_key(self, entity_type: str, entity_id: str, metric: str) -> str:
        """
        Construct Redis key for a velocity counter.

        Args:
            entity_type: Type of entity (card, device, ip, user)
            entity_id: Entity identifier
            metric: Metric name (attempts, declines, etc.)

        Returns:
            Full Redis key
        """
        return f"{self.prefix}{entity_type}:{entity_id}:{metric}"

    async def increment(
        self,
        entity_type: str,
        entity_id: str,
        metric: str,
        event_id: str,
        timestamp_ms: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """
        Add an event to the velocity counter.

        Args:
            entity_type: Type of entity (card, device, ip, user)
            entity_id: Entity identifier
            metric: Metric name
            event_id: Unique event identifier (for deduplication)
            timestamp_ms: Event timestamp in milliseconds (default: now)
            ttl_seconds: TTL for the key (default: default_ttl)

        Returns:
            Number of elements added (0 if event_id already exists)
        """
        key = self._make_key(entity_type, entity_id, metric)
        ts = timestamp_ms or int(time.time() * 1000)
        ttl = ttl_seconds or self.default_ttl

        # Use pipeline for atomic operation
        pipe = self.redis.pipeline()

        # Add event to ZSET with timestamp as score
        pipe.zadd(key, {event_id: ts})

        # Set TTL on key (refreshed on each write)
        pipe.expire(key, ttl)

        results = await pipe.execute()
        return results[0]  # Number of elements added

    async def count(
        self,
        entity_type: str,
        entity_id: str,
        metric: str,
        window_seconds: int,
    ) -> int:
        """
        Count events within a sliding time window.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            metric: Metric name
            window_seconds: Window size in seconds

        Returns:
            Count of events in the window
        """
        key = self._make_key(entity_type, entity_id, metric)
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (window_seconds * 1000)

        # Count events with score >= window_start_ms
        count = await self.redis.zcount(key, window_start_ms, now_ms)
        return count

    async def count_distinct(
        self,
        entity_type: str,
        entity_id: str,
        metric: str,
        window_seconds: int,
    ) -> int:
        """
        Count distinct values within a sliding time window.

        Uses ZSET where members are the distinct values to count.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            metric: Metric name (e.g., "distinct_cards")
            window_seconds: Window size in seconds

        Returns:
            Count of distinct values in the window
        """
        # For distinct counts, we use the same ZCOUNT approach
        # The ZSET members are the distinct values (e.g., card tokens)
        return await self.count(entity_type, entity_id, metric, window_seconds)

    async def add_distinct(
        self,
        entity_type: str,
        entity_id: str,
        metric: str,
        value: str,
        timestamp_ms: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """
        Add a value to a distinct counter.

        Unlike increment(), this uses the value itself as the member,
        so the same value won't be counted twice.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            metric: Metric name (e.g., "distinct_merchants")
            value: Value to add (e.g., merchant_id)
            timestamp_ms: Timestamp in milliseconds
            ttl_seconds: TTL for the key

        Returns:
            Number of elements added (0 if value already exists)
        """
        key = self._make_key(entity_type, entity_id, metric)
        ts = timestamp_ms or int(time.time() * 1000)
        ttl = ttl_seconds or self.default_ttl

        pipe = self.redis.pipeline()
        pipe.zadd(key, {value: ts})
        pipe.expire(key, ttl)

        results = await pipe.execute()
        return results[0]

    async def cleanup_expired(
        self,
        entity_type: str,
        entity_id: str,
        metric: str,
        max_age_seconds: int,
    ) -> int:
        """
        Remove expired events from a counter.

        This is called periodically to prevent unbounded memory growth.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            metric: Metric name
            max_age_seconds: Remove events older than this

        Returns:
            Number of elements removed
        """
        key = self._make_key(entity_type, entity_id, metric)
        cutoff_ms = int(time.time() * 1000) - (max_age_seconds * 1000)

        # Remove all events with score < cutoff
        removed = await self.redis.zremrangebyscore(key, 0, cutoff_ms)
        return removed

    async def get_all_counts(
        self,
        entity_type: str,
        entity_id: str,
        metrics: list[str],
        window_seconds: int,
    ) -> dict[str, int]:
        """
        Get counts for multiple metrics in a single round-trip.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            metrics: List of metric names
            window_seconds: Window size in seconds

        Returns:
            Dict mapping metric name to count
        """
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (window_seconds * 1000)

        # Use pipeline for efficiency
        pipe = self.redis.pipeline()
        for metric in metrics:
            key = self._make_key(entity_type, entity_id, metric)
            pipe.zcount(key, window_start_ms, now_ms)

        results = await pipe.execute()
        return dict(zip(metrics, results))


class DeclineTracker:
    """
    Tracks decline rates for entities.

    Used to detect card testing attacks where fraudsters
    probe cards with small transactions until they find working ones.
    """

    def __init__(self, velocity_counter: VelocityCounter):
        """
        Initialize decline tracker.

        Args:
            velocity_counter: Velocity counter instance
        """
        self.velocity = velocity_counter

    async def record_attempt(
        self,
        entity_type: str,
        entity_id: str,
        transaction_id: str,
        is_decline: bool,
        timestamp_ms: Optional[int] = None,
    ) -> None:
        """
        Record a transaction attempt and its outcome.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            transaction_id: Unique transaction ID
            is_decline: True if transaction was declined
            timestamp_ms: Timestamp in milliseconds
        """
        ts = timestamp_ms or int(time.time() * 1000)

        # Always record the attempt
        await self.velocity.increment(
            entity_type, entity_id, "attempts", transaction_id, ts
        )

        # Record decline if applicable
        if is_decline:
            await self.velocity.increment(
                entity_type, entity_id, "declines", transaction_id, ts
            )

    async def get_decline_rate(
        self,
        entity_type: str,
        entity_id: str,
        window_seconds: int,
    ) -> tuple[int, int, float]:
        """
        Get decline rate for an entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            window_seconds: Window size in seconds

        Returns:
            Tuple of (attempts, declines, decline_rate)
        """
        counts = await self.velocity.get_all_counts(
            entity_type, entity_id, ["attempts", "declines"], window_seconds
        )

        attempts = counts.get("attempts", 0)
        declines = counts.get("declines", 0)

        rate = declines / attempts if attempts > 0 else 0.0
        return attempts, declines, rate

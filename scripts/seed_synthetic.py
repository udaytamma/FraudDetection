"""
Synthetic Data Seeder (API-driven)

Generates synthetic transactions via the /decide endpoint and injects
chargebacks for labeled fraud. Designed for local or production use.

Robustness features:
- Per-request retry with exponential backoff (3 attempts)
- Connection pool limits tuned to concurrency level
- Explicit error logging with failure reason tracking
- Progress reporting after every batch (not just modulo checkpoints)
- Graceful handling of API overload (429/503 backpressure)
- Periodic rate reporting (txns/sec)

Notes:
- Evidence capture uses server-side captured_at (decision time).
- If you need historical maturity for training, enable
  --backdate-captured-at with a Postgres URL.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Iterable

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from loadtest.data_generator import (
    generate_transaction,
    generate_card_testing_transaction,
    generate_sim_farm_transaction,
    generate_device_resale_transaction,
    generate_equipment_fraud_transaction,
    generate_fraud_ring_transaction,
    generate_geo_anomaly_transaction,
    generate_high_value_new_subscriber_transaction,
)

try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None


FRAUD_GENERATORS = [
    generate_card_testing_transaction,
    generate_sim_farm_transaction,
    generate_device_resale_transaction,
    generate_equipment_fraud_transaction,
    generate_fraud_ring_transaction,
    generate_geo_anomaly_transaction,
    generate_high_value_new_subscriber_transaction,
]

REASON_CODES = ["10.1", "10.2", "10.3", "10.4", "10.5"]

# Retry config
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.5  # seconds, doubles each attempt
BACKPRESSURE_CODES = {429, 503, 502, 504}


@dataclass
class SeedEvent:
    payload: dict
    is_fraud: bool
    amount_cents: int
    backdate_ts: datetime | None


@dataclass
class SeedStats:
    success: int = 0
    failed: int = 0
    chargebacks: int = 0
    chargeback_failures: int = 0
    backdated: int = 0
    retries: int = 0
    error_reasons: dict = field(default_factory=dict)
    started_at: float = 0.0

    def record_error(self, reason: str) -> None:
        self.error_reasons[reason] = self.error_reasons.get(reason, 0) + 1

    def elapsed(self) -> float:
        return time.time() - self.started_at if self.started_at else 0

    def rate(self) -> float:
        elapsed = self.elapsed()
        return self.success / elapsed if elapsed > 0 else 0


# Graceful shutdown flag
_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n>>> Shutdown requested. Finishing current batch...")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed synthetic data via /decide API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=1, help="Number of seed runs")
    parser.add_argument("--per-run", type=int, default=5000, help="Transactions per run")
    parser.add_argument("--concurrency", type=int, default=50, help="Max concurrent requests")
    parser.add_argument("--fraud-rate", type=float, default=0.03, help="Fraction of fraud transactions")
    parser.add_argument("--mature-ratio", type=float, default=0.8, help="Fraction with mature timestamps")
    parser.add_argument("--maturity-days", type=int, default=120, help="Minimum age for mature txns")
    parser.add_argument("--maturity-jitter-days", type=int, default=90, help="Random jitter on mature age")
    parser.add_argument("--recent-window-days", type=int, default=120, help="Window for recent txns")
    parser.add_argument("--api-token", default=os.environ.get("API_TOKEN"))
    parser.add_argument("--auth-header", choices=["x-api-key", "authorization"], default="x-api-key")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout (seconds)")
    parser.add_argument("--log-every", type=int, default=500, help="Log progress every N transactions")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--backdate-captured-at", action="store_true",
                        help="Backdate captured_at for mature txns (requires --postgres-url)")
    parser.add_argument("--postgres-url",
                        default=os.environ.get("POSTGRES_URL",
                                               "postgresql://fraud_user:fraud_dev_password@localhost:5432/fraud_detection"))
    parser.add_argument("--chargeback-delay", type=float, default=0.5,
                        help="Seconds to wait before injecting chargebacks")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def choose_payload(is_fraud: bool) -> dict:
    if is_fraud:
        generator = random.choice(FRAUD_GENERATORS)
        return generator()
    return generate_transaction()


def assign_timestamp(
    payload: dict,
    is_mature: bool,
    maturity_days: int,
    maturity_jitter: int,
    recent_window_days: int,
    now: datetime,
) -> datetime:
    if is_mature:
        offset_days = maturity_days + random.randint(0, max(maturity_jitter, 1))
        ts = now - timedelta(days=offset_days, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    else:
        offset_days = random.randint(0, max(recent_window_days - 1, 0))
        ts = now - timedelta(days=offset_days, hours=random.randint(0, 23), minutes=random.randint(0, 59))
    payload["timestamp"] = ts.isoformat()
    return ts


def build_headers(token: str | None, auth_header: str) -> dict:
    if not token:
        return {}
    if auth_header == "authorization":
        return {"Authorization": f"Bearer {token}"}
    return {"X-API-Key": token}


def chunked(items: Iterable, size: int) -> Iterable[list]:
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def post_decide_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    item: SeedEvent,
    stats: SeedStats,
) -> tuple[bool, SeedEvent]:
    """Post /decide with retry on transient failures."""
    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(
                f"{base_url}/decide",
                json=item.payload,
                headers=headers,
            )
            if resp.status_code == 200:
                return True, item
            elif resp.status_code in BACKPRESSURE_CODES:
                # Server overloaded -- back off and retry
                delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                stats.retries += 1
                await asyncio.sleep(delay)
                last_error = f"HTTP {resp.status_code}"
                continue
            elif resp.status_code == 422:
                # Validation error -- no point retrying
                last_error = f"422 Validation"
                break
            else:
                last_error = f"HTTP {resp.status_code}"
                break
        except httpx.TimeoutException:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            stats.retries += 1
            await asyncio.sleep(delay)
            last_error = "Timeout"
        except httpx.ConnectError:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            stats.retries += 1
            await asyncio.sleep(delay)
            last_error = "ConnectError"
        except Exception as exc:
            last_error = type(exc).__name__
            break

    stats.record_error(last_error)
    return False, item


async def post_chargeback_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    transaction_id: str,
    amount_cents: int,
    stats: SeedStats,
) -> bool:
    """Post chargeback with retry."""
    payload = {
        "transaction_id": transaction_id,
        "chargeback_id": f"cb_{transaction_id}",
        "amount_cents": amount_cents,
        "reason_code": random.choice(REASON_CODES),
        "reason_description": "Synthetic fraud chargeback",
        "fraud_type": "CRIMINAL",
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(
                f"{base_url}/chargebacks",
                json=payload,
                headers=headers,
            )
            if resp.status_code in (200, 201):
                return True
            elif resp.status_code in BACKPRESSURE_CODES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                stats.retries += 1
                await asyncio.sleep(delay)
                continue
            else:
                # Non-retryable
                break
        except (httpx.TimeoutException, httpx.ConnectError):
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            stats.retries += 1
            await asyncio.sleep(delay)
        except Exception:
            break
    return False


async def backdate_rows(postgres_url: str, updates: list[tuple[datetime, str]]) -> int:
    if not updates:
        return 0
    if asyncpg is None:
        raise RuntimeError("asyncpg not available; install asyncpg to backdate rows")

    conn = await asyncpg.connect(postgres_url)
    try:
        count = 0
        for batch in chunked(updates, 500):
            await conn.executemany(
                "UPDATE transaction_evidence SET captured_at = $1 WHERE transaction_id = $2",
                batch,
            )
            count += len(batch)
            if count % 2000 == 0:
                print(f"  Backdated {count}/{len(updates)} rows...")
        return count
    finally:
        await conn.close()


def print_progress(stats: SeedStats, processed: int, total: int, phase: str = "decide") -> None:
    """Print a concise progress line with rate info."""
    pct = (processed / total) * 100 if total else 0
    rate = stats.rate()
    failed_str = f"  failed={stats.failed}" if stats.failed else ""
    retry_str = f"  retries={stats.retries}" if stats.retries else ""
    print(
        f"  [{phase}] {processed:>6}/{total} ({pct:5.1f}%)  "
        f"ok={stats.success}{failed_str}{retry_str}  "
        f"rate={rate:.0f} txn/s"
    )


async def run_seed_run(
    run_index: int,
    args: argparse.Namespace,
    stats: SeedStats,
) -> None:
    global _shutdown

    now = datetime.now(UTC)
    headers = build_headers(args.api_token, args.auth_header)

    # Build event batch
    events: list[SeedEvent] = []
    mature_count = 0
    fraud_count = 0

    print(f"\nRun {run_index}: generating {args.per_run} events...")
    for _ in range(args.per_run):
        is_fraud = random.random() < args.fraud_rate
        is_mature = random.random() < args.mature_ratio

        payload = choose_payload(is_fraud)
        amount_cents = payload.get("amount_cents", 0)
        ts = assign_timestamp(
            payload,
            is_mature,
            args.maturity_days,
            args.maturity_jitter_days,
            args.recent_window_days,
            now,
        )
        backdate_ts = ts if is_mature and args.backdate_captured_at else None

        events.append(SeedEvent(
            payload=payload,
            is_fraud=is_fraud,
            amount_cents=amount_cents,
            backdate_ts=backdate_ts,
        ))
        fraud_count += int(is_fraud)
        mature_count += int(is_mature)

    print(
        f"  Prepared: {len(events)} events "
        f"(fraud={fraud_count}, legit={len(events)-fraud_count}, "
        f"mature={mature_count}, recent={len(events)-mature_count})"
    )

    if args.dry_run:
        return

    # Configure connection pool to match concurrency
    pool_limits = httpx.Limits(
        max_connections=args.concurrency + 10,
        max_keepalive_connections=args.concurrency,
        keepalive_expiry=30,
    )
    transport = httpx.AsyncHTTPTransport(retries=0, limits=pool_limits)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(args.timeout, connect=10.0),
        transport=transport,
    ) as client:
        # ---- Phase 1: Send /decide requests ----
        print(f"\n  Phase 1: Sending {len(events)} /decide requests (concurrency={args.concurrency})...")
        processed = 0
        for batch in chunked(events, args.concurrency):
            if _shutdown:
                print("  >>> Shutdown: stopping after current batch")
                break

            results = await asyncio.gather(
                *[post_decide_with_retry(client, args.base_url, headers, item, stats) for item in batch]
            )
            for ok, item in results:
                if ok:
                    stats.success += 1
                else:
                    stats.failed += 1
            processed += len(batch)

            if args.log_every > 0 and processed % args.log_every < args.concurrency:
                print_progress(stats, processed, len(events), "decide")

        # Final progress
        print_progress(stats, processed, len(events), "decide")

        if _shutdown:
            return

        # ---- Phase 2: Inject chargebacks ----
        fraud_items = [e for e in events if e.is_fraud]
        if fraud_items:
            if args.chargeback_delay:
                print(f"\n  Waiting {args.chargeback_delay}s before chargebacks...")
                await asyncio.sleep(args.chargeback_delay)

            print(f"  Phase 2: Injecting {len(fraud_items)} chargebacks...")
            cb_processed = 0
            for batch in chunked(fraud_items, args.concurrency):
                if _shutdown:
                    break
                results = await asyncio.gather(
                    *[
                        post_chargeback_with_retry(
                            client, args.base_url, headers,
                            e.payload["transaction_id"], e.amount_cents, stats,
                        )
                        for e in batch
                    ]
                )
                ok_count = sum(1 for ok in results if ok)
                stats.chargebacks += ok_count
                stats.chargeback_failures += len(results) - ok_count
                cb_processed += len(batch)

            print(
                f"  Chargebacks: {stats.chargebacks} ok, "
                f"{stats.chargeback_failures} failed"
            )

    # ---- Phase 3: Backdate (optional) ----
    if args.backdate_captured_at and not _shutdown:
        if not args.postgres_url:
            print("  WARNING: --backdate-captured-at requires --postgres-url. Skipping.")
        else:
            updates = [(e.backdate_ts, e.payload["transaction_id"]) for e in events if e.backdate_ts]
            if updates:
                print(f"\n  Phase 3: Backdating {len(updates)} rows...")
                try:
                    updated = await backdate_rows(args.postgres_url, updates)
                    stats.backdated += updated
                    print(f"  Backdated: {updated} rows")
                except Exception as exc:
                    print(f"  ERROR backdating: {exc}")

    # Run summary
    elapsed = stats.elapsed()
    print(
        f"\nRun {run_index} complete in {elapsed:.1f}s: "
        f"success={stats.success} failed={stats.failed} "
        f"chargebacks={stats.chargebacks} backdated={stats.backdated} "
        f"retries={stats.retries}"
    )
    if stats.error_reasons:
        print("  Error breakdown:")
        for reason, count in sorted(stats.error_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")


async def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    stats = SeedStats()
    stats.started_at = time.time()

    print("=" * 60)
    print("SYNTHETIC DATA SEEDER")
    print("=" * 60)
    print(f"  Target:       {args.base_url}")
    print(f"  Runs:         {args.runs} x {args.per_run} = {args.runs * args.per_run} txns")
    print(f"  Concurrency:  {args.concurrency}")
    print(f"  Fraud rate:   {args.fraud_rate*100:.1f}%")
    print(f"  Mature ratio: {args.mature_ratio*100:.0f}% (>{args.maturity_days}d old)")
    print(f"  Backdate:     {'Yes' if args.backdate_captured_at else 'No'}")
    print(f"  Timeout:      {args.timeout}s per request")
    print(f"  Retries:      {MAX_RETRIES} per request")
    print("=" * 60)

    for i in range(1, args.runs + 1):
        if _shutdown:
            print(">>> Shutdown requested. Skipping remaining runs.")
            break
        await run_seed_run(i, args, stats)

    elapsed = stats.elapsed()
    print()
    print("=" * 60)
    print("SEED COMPLETE")
    print("=" * 60)
    print(f"  Total time:     {elapsed:.1f}s")
    print(f"  Decisions:      {stats.success} ok, {stats.failed} failed")
    print(f"  Chargebacks:    {stats.chargebacks} ok, {stats.chargeback_failures} failed")
    print(f"  Backdated:      {stats.backdated} rows")
    print(f"  Retries:        {stats.retries}")
    print(f"  Avg rate:       {stats.rate():.0f} txn/s")
    if stats.error_reasons:
        print("  Errors:")
        for reason, count in sorted(stats.error_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

"""
Synthetic Data Seeder (API-driven)

Generates synthetic transactions via the /decide endpoint and injects
chargebacks for labeled fraud. Designed for local or production use.

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
import sys
from dataclasses import dataclass
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


@dataclass
class SeedEvent:
    payload: dict
    is_fraud: bool
    amount_cents: int
    backdate_ts: datetime | None


class SeedStats:
    def __init__(self) -> None:
        self.success = 0
        self.failed = 0
        self.chargebacks = 0
        self.backdated = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed synthetic data via /decide")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--per-run", type=int, default=50000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--fraud-rate", type=float, default=0.03)
    parser.add_argument("--mature-ratio", type=float, default=0.8)
    parser.add_argument("--maturity-days", type=int, default=120)
    parser.add_argument("--maturity-jitter-days", type=int, default=90)
    parser.add_argument("--recent-window-days", type=int, default=120)
    parser.add_argument("--api-token", default=os.environ.get("API_TOKEN"))
    parser.add_argument("--auth-header", choices=["x-api-key", "authorization"], default="x-api-key")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--log-every", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--backdate-captured-at", action="store_true")
    parser.add_argument("--postgres-url", default=os.environ.get("POSTGRES_URL"))
    parser.add_argument("--chargeback-delay", type=float, default=0.0)
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
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def post_decide(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    item: SeedEvent,
) -> tuple[bool, SeedEvent]:
    try:
        resp = await client.post(f"{base_url}/decide", json=item.payload, headers=headers)
        resp.raise_for_status()
        return True, item
    except Exception:
        return False, item


async def post_chargeback(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    transaction_id: str,
    amount_cents: int,
) -> bool:
    payload = {
        "transaction_id": transaction_id,
        "chargeback_id": f"cb_{transaction_id}",
        "amount_cents": amount_cents,
        "reason_code": random.choice(REASON_CODES),
        "reason_description": "Synthetic fraud chargeback",
        "fraud_type": "CRIMINAL",
    }
    try:
        resp = await client.post(f"{base_url}/chargebacks", json=payload, headers=headers)
        resp.raise_for_status()
        return True
    except Exception:
        return False


async def backdate_rows(postgres_url: str, updates: list[tuple[datetime, str]]) -> int:
    if not updates:
        return 0
    if asyncpg is None:
        raise RuntimeError("asyncpg not available; install asyncpg to backdate rows")

    conn = await asyncpg.connect(postgres_url)
    try:
        for batch in chunked(updates, 1000):
            await conn.executemany(
                "UPDATE transaction_evidence SET captured_at = $1 WHERE transaction_id = $2",
                batch,
            )
        return len(updates)
    finally:
        await conn.close()


async def run_seed_run(
    run_index: int,
    args: argparse.Namespace,
    stats: SeedStats,
) -> None:
    now = datetime.now(UTC)
    headers = build_headers(args.api_token, args.auth_header)

    events: list[SeedEvent] = []
    mature_count = 0
    fraud_count = 0

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

        events.append(SeedEvent(payload=payload, is_fraud=is_fraud, amount_cents=amount_cents, backdate_ts=backdate_ts))
        fraud_count += int(is_fraud)
        mature_count += int(is_mature)

    if args.dry_run:
        print(f"Run {run_index}: prepared {len(events)} events (fraud={fraud_count}, mature={mature_count})")
        return

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        # Step 1: /decide for all events
        processed = 0
        for batch in chunked(events, args.concurrency):
            results = await asyncio.gather(
                *[post_decide(client, args.base_url, headers, item) for item in batch]
            )
            for ok, item in results:
                if ok:
                    stats.success += 1
                else:
                    stats.failed += 1
            processed += len(batch)
            if args.log_every > 0 and processed % args.log_every == 0:
                percent = (processed / len(events)) * 100
                print(f"Run {run_index}: processed {processed}/{len(events)} ({percent:.1f}%)")

        # Step 2: optional chargeback delay
        if args.chargeback_delay:
            await asyncio.sleep(args.chargeback_delay)

        # Step 3: inject chargebacks for fraud events
        fraud_items = [e for e in events if e.is_fraud]
        for batch in chunked(fraud_items, args.concurrency):
            results = await asyncio.gather(
                *[
                    post_chargeback(client, args.base_url, headers, e.payload["transaction_id"], e.amount_cents)
                    for e in batch
                ]
            )
            stats.chargebacks += sum(1 for ok in results if ok)

    # Step 4: backdate captured_at (optional)
    if args.backdate_captured_at:
        if not args.postgres_url:
            raise RuntimeError("--backdate-captured-at requires --postgres-url or POSTGRES_URL env")
        updates = [(e.backdate_ts, e.payload["transaction_id"]) for e in events if e.backdate_ts]
        updated = await backdate_rows(args.postgres_url, updates)
        stats.backdated += updated

    print(
        f"Run {run_index} complete: success={stats.success} failed={stats.failed} "
        f"chargebacks={stats.chargebacks} backdated={stats.backdated}"
    )


async def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    stats = SeedStats()
    for i in range(1, args.runs + 1):
        await run_seed_run(i, args, stats)

    print(
        "Summary: "
        f"success={stats.success} failed={stats.failed} "
        f"chargebacks={stats.chargebacks} backdated={stats.backdated}"
    )


if __name__ == "__main__":
    asyncio.run(main())

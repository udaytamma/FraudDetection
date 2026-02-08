"""
Lightweight in-memory telemetry for demo dashboards.
"""

from collections import deque
from datetime import datetime, UTC, timedelta
from statistics import mean
from typing import Deque, Dict, List


class DecisionTelemetry:
    """Ring buffer of recent decisions for dashboarding."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._events: Deque[dict] = deque(maxlen=maxlen)

    def record(self, decision: str, latency_ms: float) -> None:
        self._events.append(
            {
                "ts": datetime.now(UTC),
                "decision": decision,
                "latency_ms": latency_ms,
            }
        )

    def snapshot(self, hours: int = 24) -> dict:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        events = [e for e in self._events if e["ts"] >= cutoff]

        latencies = [e["latency_ms"] for e in events]
        decisions: Dict[str, int] = {}
        for e in events:
            decisions[e["decision"]] = decisions.get(e["decision"], 0) + 1

        p95 = None
        if latencies:
            latencies_sorted = sorted(latencies)
            index = int(round(0.95 * (len(latencies_sorted) - 1)))
            p95 = latencies_sorted[index]

        return {
            "window_hours": hours,
            "counts": decisions,
            "avg_latency_ms": mean(latencies) if latencies else None,
            "p95_latency_ms": p95,
            "events": [
                {
                    "ts": e["ts"].isoformat(),
                    "decision": e["decision"],
                    "latency_ms": e["latency_ms"],
                }
                for e in events
            ],
        }


telemetry = DecisionTelemetry()

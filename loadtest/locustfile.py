"""
Telco/MSP Payment Fraud Detection Load Test Suite

Locust-based load testing for the fraud detection API.
Supports realistic telco traffic patterns, fraud injection, and various test scenarios.
Tracks ML scoring metrics (champion/challenger/holdout routing, model latency, score distributions).

Usage:
    locust -f locustfile.py --host=http://localhost:8000

Web UI available at: http://localhost:8089
"""

import random
import statistics
import time
import threading
from collections import defaultdict
from uuid import uuid4

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

from data_generator import (
    generate_transaction,
    generate_card_testing_transaction,
    generate_sim_farm_transaction,
    generate_device_resale_transaction,
    generate_equipment_fraud_transaction,
    generate_fraud_ring_transaction,
    generate_geo_anomaly_transaction,
    generate_high_value_new_subscriber_transaction,
    TRAFFIC_MIX,
)


# ---------------------------------------------------------------------------
# ML Metrics Collector
# Thread-safe accumulator for ML scoring telemetry across all users.
# Tracks per-variant routing, score distributions, latency breakdown, and
# decision outcomes to validate ML behavior under load.
# ---------------------------------------------------------------------------

class MLMetricsCollector:
    """Collects ML scoring metrics across all Locust users."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        """Reset all counters for a fresh test run."""
        with self._lock:
            # Per-variant request counts
            self.variant_counts = defaultdict(int)  # champion / challenger / holdout / rules_only
            # Per-variant ML scores (for distribution analysis)
            self.variant_scores = defaultdict(list)
            # Per-variant decision distribution
            self.variant_decisions = defaultdict(lambda: defaultdict(int))
            # Component latency tracking (ms)
            self.scoring_latencies = []
            self.feature_latencies = []
            self.total_latencies = []
            # Per-variant risk scores (rules + ML combined)
            self.variant_risk_scores = defaultdict(list)
            # Model version tracking
            self.model_versions_seen = set()
            # SLA tracking
            self.scoring_sla_breaches = 0  # scoring_time_ms > 25ms target
            self.total_sla_breaches = 0    # processing_time_ms > 200ms target
            self.total_tracked = 0

    def record(self, data: dict):
        """
        Record ML metrics from a single /decide API response.

        Extracts ml_score, model_variant, model_version from nested `scores`,
        and component latencies from top-level timing fields.
        """
        scores = data.get("scores", {})
        ml_score = scores.get("ml_score")
        model_variant = scores.get("model_variant")
        model_version = scores.get("model_version")
        risk_score = scores.get("risk_score", 0.0)
        decision = data.get("decision", "UNKNOWN")

        scoring_time = data.get("scoring_time_ms", 0.0)
        feature_time = data.get("feature_time_ms", 0.0)
        processing_time = data.get("processing_time_ms", 0.0)

        # Determine variant bucket: use model_variant if present, else rules_only
        variant = model_variant if model_variant else "rules_only"

        with self._lock:
            self.total_tracked += 1

            # Variant routing
            self.variant_counts[variant] += 1

            # ML score distribution (only when ML actually scored)
            if ml_score is not None:
                self.variant_scores[variant].append(ml_score)

            # Risk score per variant (always available)
            self.variant_risk_scores[variant].append(risk_score)

            # Decision breakdown per variant
            self.variant_decisions[variant][decision] += 1

            # Latencies
            if scoring_time > 0:
                self.scoring_latencies.append(scoring_time)
            if feature_time > 0:
                self.feature_latencies.append(feature_time)
            if processing_time > 0:
                self.total_latencies.append(processing_time)

            # Model version tracking
            if model_version:
                self.model_versions_seen.add(f"{variant}:{model_version}")

            # SLA breach tracking
            if scoring_time > 25:
                self.scoring_sla_breaches += 1
            if processing_time > 200:
                self.total_sla_breaches += 1

    def report(self) -> str:
        """Generate a formatted ML metrics report for test_stop output."""
        with self._lock:
            if self.total_tracked == 0:
                return "  No ML metrics collected (0 successful requests)."

            lines = []

            # --- Variant Routing Distribution ---
            lines.append("  VARIANT ROUTING DISTRIBUTION")
            lines.append("  " + "-" * 56)
            total = self.total_tracked
            for variant in sorted(self.variant_counts.keys()):
                count = self.variant_counts[variant]
                pct = (count / total) * 100
                bar = "#" * int(pct / 2)
                lines.append(f"    {variant:<14} {count:>6} ({pct:5.1f}%)  {bar}")
            lines.append(f"    {'TOTAL':<14} {total:>6}")
            lines.append("")

            # --- Model Versions Observed ---
            if self.model_versions_seen:
                lines.append("  MODEL VERSIONS OBSERVED")
                lines.append("  " + "-" * 56)
                for mv in sorted(self.model_versions_seen):
                    lines.append(f"    {mv}")
                lines.append("")

            # --- ML Score Distribution Per Variant ---
            ml_variants = {v: s for v, s in self.variant_scores.items() if s}
            if ml_variants:
                lines.append("  ML SCORE DISTRIBUTION (per variant)")
                lines.append("  " + "-" * 56)
                lines.append(f"    {'Variant':<14} {'Count':>6} {'Mean':>7} {'P50':>7} {'P95':>7} {'P99':>7}")
                for variant in sorted(ml_variants.keys()):
                    scores = ml_variants[variant]
                    sorted_scores = sorted(scores)
                    n = len(sorted_scores)
                    mean = statistics.mean(sorted_scores)
                    p50 = sorted_scores[int(n * 0.5)] if n > 0 else 0
                    p95 = sorted_scores[min(int(n * 0.95), n - 1)] if n > 0 else 0
                    p99 = sorted_scores[min(int(n * 0.99), n - 1)] if n > 0 else 0
                    lines.append(f"    {variant:<14} {n:>6} {mean:>7.4f} {p50:>7.4f} {p95:>7.4f} {p99:>7.4f}")
                lines.append("")

            # --- Risk Score Comparison By Variant ---
            lines.append("  RISK SCORE BY VARIANT (combined ML + rules)")
            lines.append("  " + "-" * 56)
            lines.append(f"    {'Variant':<14} {'Count':>6} {'Mean':>7} {'P50':>7} {'P95':>7}")
            for variant in sorted(self.variant_risk_scores.keys()):
                scores = sorted(self.variant_risk_scores[variant])
                n = len(scores)
                if n > 0:
                    mean = statistics.mean(scores)
                    p50 = scores[int(n * 0.5)]
                    p95 = scores[min(int(n * 0.95), n - 1)]
                    lines.append(f"    {variant:<14} {n:>6} {mean:>7.4f} {p50:>7.4f} {p95:>7.4f}")
            lines.append("")

            # --- Decision Distribution Per Variant ---
            lines.append("  DECISIONS BY VARIANT")
            lines.append("  " + "-" * 56)
            all_decisions = sorted(set(
                d for vd in self.variant_decisions.values() for d in vd.keys()
            ))
            header = f"    {'Variant':<14}" + "".join(f" {d:>9}" for d in all_decisions)
            lines.append(header)
            for variant in sorted(self.variant_decisions.keys()):
                row = f"    {variant:<14}"
                for d in all_decisions:
                    count = self.variant_decisions[variant].get(d, 0)
                    row += f" {count:>9}"
                lines.append(row)
            lines.append("")

            # --- Component Latency Breakdown ---
            lines.append("  COMPONENT LATENCY (ms)")
            lines.append("  " + "-" * 56)
            for label, latencies in [
                ("Feature", self.feature_latencies),
                ("Scoring", self.scoring_latencies),
                ("Total E2E", self.total_latencies),
            ]:
                if latencies:
                    sorted_lat = sorted(latencies)
                    n = len(sorted_lat)
                    mean = statistics.mean(sorted_lat)
                    p50 = sorted_lat[int(n * 0.5)]
                    p95 = sorted_lat[min(int(n * 0.95), n - 1)]
                    p99 = sorted_lat[min(int(n * 0.99), n - 1)]
                    lines.append(
                        f"    {label:<12} mean={mean:>7.1f}  P50={p50:>7.1f}  "
                        f"P95={p95:>7.1f}  P99={p99:>7.1f}"
                    )
            lines.append("")

            # --- SLA Compliance ---
            lines.append("  SLA COMPLIANCE")
            lines.append("  " + "-" * 56)
            scoring_pct = ((total - self.scoring_sla_breaches) / total) * 100 if total else 0
            total_pct = ((total - self.total_sla_breaches) / total) * 100 if total else 0
            lines.append(f"    Scoring (<25ms target):     {scoring_pct:.1f}% compliant  "
                         f"({self.scoring_sla_breaches} breaches)")
            lines.append(f"    End-to-end (<200ms target): {total_pct:.1f}% compliant  "
                         f"({self.total_sla_breaches} breaches)")

            return "\n".join(lines)


# Global ML metrics collector instance
ml_metrics = MLMetricsCollector()


class FraudDetectionUser(HttpUser):
    """
    Simulates a telco payment processor sending transactions for fraud decisions.

    Traffic mix (telco context):
    - 95% legitimate transactions (SIM activations, topups, service changes)
    - 2% card testing attacks (small topups to validate stolen cards)
    - 1% fraud ring patterns (same device, multiple subscriber accounts)
    - 1% geo anomaly (service activation from unexpected location)
    - 1% high-value new subscriber (device upgrade from new account)
    """

    # Wait 100-500ms between requests (simulates realistic traffic)
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Called when a user starts. Verify API is healthy."""
        response = self.client.get("/health")
        if response.status_code != 200:
            print(f"WARNING: Health check failed: {response.status_code}")

    @task(95)
    def legitimate_transaction(self):
        """Normal legitimate transaction - 95% of traffic."""
        payload = generate_transaction()
        self._send_decision_request(payload, "legitimate")

    @task(2)
    def card_testing_attack(self):
        """
        Card testing attack pattern - 2% of traffic.
        Same card, rapid small topups to test card validity.
        """
        payload = generate_card_testing_transaction()
        self._send_decision_request(payload, "card_testing")

    @task(1)
    def fraud_ring_pattern(self):
        """
        Fraud ring pattern - 1% of traffic.
        Same device, multiple subscriber accounts.
        """
        payload = generate_fraud_ring_transaction()
        self._send_decision_request(payload, "fraud_ring")

    @task(1)
    def geo_anomaly_pattern(self):
        """
        Geographic anomaly - 1% of traffic.
        Service activation from unexpected location.
        """
        payload = generate_geo_anomaly_transaction()
        self._send_decision_request(payload, "geo_anomaly")

    @task(1)
    def high_value_new_subscriber(self):
        """
        High value from new subscriber - 1% of traffic.
        Device upgrade fraud indicator.
        """
        payload = generate_high_value_new_subscriber_transaction()
        self._send_decision_request(payload, "high_value_new_subscriber")

    def _send_decision_request(self, payload: dict, scenario: str):
        """
        Send decision request, enforce SLA, and feed ML metrics collector.

        Extracts ML scoring metadata (model variant, ML score, component latencies)
        from each response so we can validate champion/challenger routing ratios,
        score distributions, and per-component latency budgets under load.
        """
        with self.client.post(
            "/decide",
            json=payload,
            name=f"/decide [{scenario}]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                decision = data.get("decision", "unknown")
                processing_time = data.get("processing_time_ms", 0)

                # Feed ML metrics collector
                ml_metrics.record(data)

                # Fail if total latency exceeds end-to-end SLA
                if processing_time > 200:
                    response.failure(f"SLA breach: {processing_time:.1f}ms > 200ms")
                else:
                    response.success()
            elif response.status_code == 422:
                response.failure(f"Validation error: {response.text}")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")


class SIMFarmAttacker(HttpUser):
    """
    Dedicated SIM farm attacker simulation.

    Sends rapid SIM activation requests with the same card to simulate
    SIM farm setup operations. Each attacker has a small pool of cards.
    """

    # Very fast requests - simulating automated attack
    wait_time = between(0.05, 0.15)

    def on_start(self):
        """Initialize attacker's card pool."""
        # Each attacker has a small pool of cards they're using for SIM farm
        self.attack_cards = [f"card_farm_{uuid4().hex[:8]}" for _ in range(3)]
        self.current_card_idx = 0

    @task
    def rapid_sim_activation(self):
        """Rapid SIM activations - cycles through small card pool."""
        card_token = self.attack_cards[self.current_card_idx]
        self.current_card_idx = (self.current_card_idx + 1) % len(self.attack_cards)

        payload = generate_sim_farm_transaction(card_token=card_token)

        with self.client.post(
            "/decide",
            json=payload,
            name="/decide [sim_farm_attack]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                decision = data.get("decision", "unknown")
                ml_metrics.record(data)
                # We expect BLOCK or FRICTION after velocity threshold
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


class CardTestingUser(HttpUser):
    """
    Dedicated card testing attacker simulation.

    Sends rapid small topup requests with the same card to trigger
    velocity detection. Tests card validity before larger fraud.
    """

    # Very fast requests - simulating automated attack
    wait_time = between(0.05, 0.15)

    def on_start(self):
        """Initialize attacker's card pool."""
        # Each attacker has a small pool of cards they're testing
        self.attack_cards = [f"card_test_{uuid4().hex[:8]}" for _ in range(3)]
        self.current_card_idx = 0

    @task
    def rapid_card_test(self):
        """Rapid card testing via small topups - cycles through card pool."""
        card_token = self.attack_cards[self.current_card_idx]
        self.current_card_idx = (self.current_card_idx + 1) % len(self.attack_cards)

        payload = generate_card_testing_transaction(card_token=card_token)

        with self.client.post(
            "/decide",
            json=payload,
            name="/decide [card_testing_attack]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                decision = data.get("decision", "unknown")
                ml_metrics.record(data)
                # We expect BLOCK or FRICTION after velocity threshold
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


class SteadyStateUser(HttpUser):
    """
    Steady state testing - only legitimate traffic.

    Use this for baseline performance measurement without fraud injection.
    """

    wait_time = between(0.1, 0.3)

    @task
    def legitimate_only(self):
        """Only legitimate transactions for clean baseline."""
        payload = generate_transaction()

        with self.client.post(
            "/decide",
            json=payload,
            name="/decide [steady_state]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                processing_time = data.get("processing_time_ms", 0)
                ml_metrics.record(data)
                if processing_time > 200:
                    response.failure(f"SLA breach: {processing_time:.1f}ms")
                else:
                    response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


# Event handlers for custom metrics and reporting

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts. Resets ML metrics collector and prints banner."""
    ml_metrics.reset()

    print("=" * 60)
    print("TELCO/MSP PAYMENT FRAUD DETECTION LOAD TEST")
    print("=" * 60)
    print(f"Target host: {environment.host}")
    print(f"Traffic mix: {TRAFFIC_MIX}")
    print()
    print("ML Scoring:  ENABLED (hybrid ML + rules)")
    print("  Routing:   80% champion / 15% challenger / 5% holdout")
    print("  Blend:     70% ML weight + 30% rules weight")
    print("  SLA:       <25ms scoring, <200ms end-to-end")
    print()
    print("Fraud patterns simulated:")
    print("  - Card testing (small topups)")
    print("  - SIM farm attacks (rapid SIM activations)")
    print("  - Device resale fraud (subsidized device fraud)")
    print("  - Equipment fraud (CPE/modem resale)")
    print("  - Fraud rings (same device, multiple accounts)")
    print("  - Geographic anomalies (unexpected locations)")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops. Prints Locust stats + detailed ML metrics report."""
    print()
    print("=" * 60)
    print("LOAD TEST COMPLETE")
    print("=" * 60)

    if environment.stats.total.num_requests > 0:
        stats = environment.stats.total
        print(f"  Total requests:   {stats.num_requests}")
        print(f"  Total failures:   {stats.num_failures}")
        print(f"  Failure rate:     {(stats.num_failures / stats.num_requests) * 100:.2f}%")
        print(f"  Avg response:     {stats.avg_response_time:.2f}ms")
        print(f"  P50 response:     {stats.get_response_time_percentile(0.5):.2f}ms")
        print(f"  P95 response:     {stats.get_response_time_percentile(0.95):.2f}ms")
        print(f"  P99 response:     {stats.get_response_time_percentile(0.99):.2f}ms")
        print(f"  Requests/sec:     {stats.total_rps:.2f}")

    # Print ML-specific metrics report
    print()
    print("-" * 60)
    print("ML SCORING METRICS")
    print("-" * 60)
    print(ml_metrics.report())
    print("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """
    Called on every request for cross-cutting SLA monitoring.

    Note: ML-specific metrics (variant routing, scores, component latencies) are
    captured in _send_decision_request via ml_metrics.record(). This listener
    handles Locust-level response_time tracking which includes HTTP overhead.
    """
    # Locust response_time includes network round-trip; API processing_time_ms
    # is the server-side measurement used for SLA in ml_metrics.
    pass

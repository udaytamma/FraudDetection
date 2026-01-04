"""
Fraud Detection Load Test Suite

Locust-based load testing for the fraud detection API.
Supports realistic traffic patterns, fraud injection, and various test scenarios.

Usage:
    locust -f locustfile.py --host=http://localhost:8000

Web UI available at: http://localhost:8089
"""

import random
import time
from uuid import uuid4

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

from data_generator import (
    generate_transaction,
    generate_card_testing_transaction,
    generate_fraud_ring_transaction,
    generate_geo_anomaly_transaction,
    generate_high_value_new_user_transaction,
    TRAFFIC_MIX,
)


class FraudDetectionUser(HttpUser):
    """
    Simulates a payment processor sending transactions for fraud decisions.

    Traffic mix:
    - 95% legitimate transactions
    - 2% card testing attacks
    - 1% fraud ring patterns
    - 1% geo anomaly
    - 1% high-value new user
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
        Same card, rapid small transactions.
        """
        payload = generate_card_testing_transaction()
        self._send_decision_request(payload, "card_testing")

    @task(1)
    def fraud_ring_pattern(self):
        """
        Fraud ring pattern - 1% of traffic.
        Same device, different cards.
        """
        payload = generate_fraud_ring_transaction()
        self._send_decision_request(payload, "fraud_ring")

    @task(1)
    def geo_anomaly_pattern(self):
        """
        Geographic anomaly - 1% of traffic.
        Transaction from unexpected location.
        """
        payload = generate_geo_anomaly_transaction()
        self._send_decision_request(payload, "geo_anomaly")

    @task(1)
    def high_value_new_user(self):
        """
        High value from new user - 1% of traffic.
        Potential friendly fraud indicator.
        """
        payload = generate_high_value_new_user_transaction()
        self._send_decision_request(payload, "high_value_new_user")

    def _send_decision_request(self, payload: dict, scenario: str):
        """Send decision request and track metrics."""
        with self.client.post(
            "/decide",
            json=payload,
            name=f"/decide [{scenario}]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Track decision distribution
                decision = data.get("decision", "unknown")
                processing_time = data.get("processing_time_ms", 0)

                # Fail if latency exceeds SLA
                if processing_time > 200:
                    response.failure(f"SLA breach: {processing_time}ms > 200ms")
                else:
                    response.success()
            elif response.status_code == 422:
                # Validation error - log but don't fail the test
                response.failure(f"Validation error: {response.text}")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")


class CardTestingUser(HttpUser):
    """
    Dedicated card testing attacker simulation.

    Sends rapid requests with the same card to trigger velocity detection.
    Use this user class for targeted card testing attack simulation.
    """

    # Very fast requests - simulating automated attack
    wait_time = between(0.05, 0.15)

    def on_start(self):
        """Initialize attacker's card pool."""
        # Each attacker has a small pool of cards they're testing
        self.attack_cards = [f"card_attack_{uuid4().hex[:8]}" for _ in range(3)]
        self.current_card_idx = 0

    @task
    def rapid_card_test(self):
        """Rapid card testing - cycles through small card pool."""
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
                if processing_time > 200:
                    response.failure(f"SLA breach: {processing_time}ms")
                else:
                    response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


# Event handlers for custom metrics and reporting

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print("=" * 60)
    print("FRAUD DETECTION LOAD TEST")
    print("=" * 60)
    print(f"Target host: {environment.host}")
    print(f"Traffic mix: {TRAFFIC_MIX}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("=" * 60)
    print("LOAD TEST COMPLETE")
    print("=" * 60)

    if environment.stats.total.num_requests > 0:
        stats = environment.stats.total
        print(f"Total requests: {stats.num_requests}")
        print(f"Total failures: {stats.num_failures}")
        print(f"Failure rate: {(stats.num_failures / stats.num_requests) * 100:.2f}%")
        print(f"Avg response time: {stats.avg_response_time:.2f}ms")
        print(f"P50 response time: {stats.get_response_time_percentile(0.5):.2f}ms")
        print(f"P95 response time: {stats.get_response_time_percentile(0.95):.2f}ms")
        print(f"P99 response time: {stats.get_response_time_percentile(0.99):.2f}ms")
        print(f"Requests/sec: {stats.total_rps:.2f}")
    print("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Called on every request - can be used for custom tracking."""
    # Track SLA breaches
    if response_time > 200:
        # Could log to file or send to monitoring system
        pass

"""
Realistic Transaction Data Generator

Generates payment transactions with realistic distributions for load testing.
Supports various fraud patterns and legitimate traffic simulation.
"""

import random
from datetime import datetime, UTC
from uuid import uuid4
from typing import Optional


# =============================================================================
# CONFIGURATION - Realistic distributions based on production patterns
# =============================================================================

# Transaction amount distribution (in cents)
# Real payments are heavily skewed toward smaller amounts
AMOUNT_DISTRIBUTION = [
    ((1, 1000), 0.40),       # $0.01-$10.00 (40% of transactions)
    ((1001, 5000), 0.30),    # $10.01-$50.00 (30%)
    ((5001, 20000), 0.20),   # $50.01-$200.00 (20%)
    ((20001, 100000), 0.08), # $200.01-$1000.00 (8%)
    ((100001, 500000), 0.02) # $1000.01-$5000.00 (2%)
]

# Entity pool sizes - controls cardinality for velocity patterns
POOL_SIZES = {
    "cards": 10000,
    "devices": 5000,
    "ips": 2000,
    "users": 8000,
    "merchants": 500,
}

# Traffic mix percentages
TRAFFIC_MIX = {
    "legitimate": 0.95,
    "card_testing": 0.02,
    "fraud_ring": 0.01,
    "geo_anomaly": 0.01,
    "high_value_new_user": 0.01,
}

# Card brands and their distribution
CARD_BRANDS = [
    ("Visa", 0.50),
    ("Mastercard", 0.30),
    ("Amex", 0.10),
    ("Discover", 0.05),
    ("Other", 0.05),
]

# Device types
DEVICE_TYPES = [
    ("mobile", 0.60),
    ("desktop", 0.35),
    ("tablet", 0.05),
]

# Operating systems
OS_TYPES = [
    ("iOS", 0.35),
    ("Android", 0.30),
    ("Windows", 0.20),
    ("macOS", 0.10),
    ("Linux", 0.05),
]

# Countries (for geo distribution)
COUNTRIES = [
    ("US", 0.70),
    ("CA", 0.10),
    ("GB", 0.08),
    ("DE", 0.05),
    ("FR", 0.04),
    ("AU", 0.03),
]

# High-risk MCCs
HIGH_RISK_MCCS = ["5967", "5966", "7995", "5816", "4829"]

# Merchant categories
MERCHANT_MCCS = [
    ("5411", 0.30),  # Grocery stores
    ("5812", 0.20),  # Restaurants
    ("5311", 0.15),  # Department stores
    ("5912", 0.10),  # Drug stores
    ("5541", 0.10),  # Gas stations
    ("5999", 0.15),  # Misc retail
]


# =============================================================================
# ENTITY POOLS - Pre-generated for consistent velocity patterns
# =============================================================================

# Initialize pools with deterministic IDs for reproducibility
_card_pool = [f"card_{i:05d}" for i in range(POOL_SIZES["cards"])]
_device_pool = [f"device_{i:05d}" for i in range(POOL_SIZES["devices"])]
_ip_pool = [f"192.168.{i // 256}.{i % 256}" for i in range(POOL_SIZES["ips"])]
_user_pool = [f"user_{i:05d}" for i in range(POOL_SIZES["users"])]
_merchant_pool = [f"merchant_{i:03d}" for i in range(POOL_SIZES["merchants"])]

# Shared state for attack patterns
_card_testing_cards = {}  # card_id -> request_count
_fraud_ring_devices = {}  # device_id -> cards_used


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def weighted_choice(choices: list) -> any:
    """Select from weighted choices list."""
    values, weights = zip(*choices)
    return random.choices(values, weights=weights, k=1)[0]


def generate_amount() -> int:
    """Generate realistic transaction amount in cents."""
    range_tuple = weighted_choice(AMOUNT_DISTRIBUTION)
    return random.randint(range_tuple[0], range_tuple[1])


def get_random_card() -> str:
    """Get a random card from the pool."""
    return random.choice(_card_pool)


def get_random_device() -> str:
    """Get a random device from the pool."""
    return random.choice(_device_pool)


def get_random_ip() -> str:
    """Get a random IP from the pool."""
    return random.choice(_ip_pool)


def get_random_user() -> str:
    """Get a random user from the pool."""
    return random.choice(_user_pool)


def get_random_merchant() -> str:
    """Get a random merchant from the pool."""
    return random.choice(_merchant_pool)


# =============================================================================
# TRANSACTION GENERATORS
# =============================================================================

def generate_transaction(
    card_token: Optional[str] = None,
    device_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    is_high_value: bool = False,
    is_new_user: bool = False,
    is_vpn: bool = False,
    is_emulator: bool = False,
    country_code: Optional[str] = None,
) -> dict:
    """
    Generate a realistic payment transaction.

    Args:
        card_token: Specific card token (or random from pool)
        device_id: Specific device ID (or random from pool)
        ip_address: Specific IP (or random from pool)
        user_id: Specific user (or random from pool)
        amount_cents: Specific amount (or realistic distribution)
        is_high_value: Force high-value transaction
        is_new_user: Force new user (low account age)
        is_vpn: Mark as VPN traffic
        is_emulator: Mark as emulator device
        country_code: Specific country (or weighted random)

    Returns:
        dict: Transaction payload ready for /decide endpoint
    """
    transaction_id = uuid4().hex
    idempotency_key = f"idem_{transaction_id}"

    # Use provided values or generate
    card = card_token or get_random_card()
    device = device_id or get_random_device()
    ip = ip_address or get_random_ip()
    user = user_id or get_random_user()

    if amount_cents:
        amount = amount_cents
    elif is_high_value:
        amount = random.randint(100000, 500000)  # $1000-$5000
    else:
        amount = generate_amount()

    country = country_code or weighted_choice(COUNTRIES)
    device_type = weighted_choice(DEVICE_TYPES)
    os_type = weighted_choice(OS_TYPES)
    card_brand = weighted_choice(CARD_BRANDS)
    mcc = weighted_choice(MERCHANT_MCCS)

    # Account age - most users are established, some are new
    if is_new_user:
        account_age = random.randint(0, 7)
    else:
        account_age = random.randint(30, 1000)

    return {
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "event_type": "authorization",
        "timestamp": datetime.now(UTC).isoformat(),
        "amount_cents": amount,
        "currency": "USD",
        "card_token": card,
        "card_bin": f"{random.randint(400000, 499999)}",
        "card_last_four": f"{random.randint(1000, 9999)}",
        "card_brand": card_brand,
        "card_type": random.choice(["credit", "debit"]),
        "card_country": country,
        "merchant_id": get_random_merchant(),
        "merchant_name": f"Test Merchant {random.randint(1, 100)}",
        "merchant_mcc": mcc,
        "merchant_country": "US",
        "user_id": user,
        "account_age_days": account_age,
        "is_guest": random.random() < 0.1,  # 10% guest checkout
        "device": {
            "device_id": device,
            "device_type": device_type,
            "os": os_type,
            "os_version": f"{random.randint(10, 17)}.{random.randint(0, 5)}",
            "browser": random.choice(["Chrome", "Safari", "Firefox", "Edge"]),
            "browser_version": f"{random.randint(90, 120)}.0",
            "is_emulator": is_emulator,
            "is_rooted": random.random() < 0.01,  # 1% rooted
            "screen_resolution": random.choice(["1920x1080", "1440x900", "375x812"]),
            "timezone": "America/New_York",
            "language": "en-US",
        },
        "geo": {
            "ip_address": ip,
            "country_code": country,
            "region": random.choice(["CA", "NY", "TX", "FL", "WA"]),
            "city": random.choice(["Los Angeles", "New York", "Houston", "Miami", "Seattle"]),
            "latitude": round(random.uniform(25.0, 48.0), 4),
            "longitude": round(random.uniform(-125.0, -70.0), 4),
            "is_vpn": is_vpn,
            "is_proxy": False,
            "is_datacenter": random.random() < 0.02,  # 2% datacenter
            "is_tor": False,
        },
        "verification": {
            "avs_result": random.choice(["Y", "Y", "Y", "N", "A"]),  # Mostly match
            "cvv_result": random.choice(["M", "M", "M", "N"]),  # Mostly match
            "three_ds_result": None,  # Not always present
        },
        "channel": random.choice(["web", "mobile", "api"]),
        "is_recurring": random.random() < 0.15,  # 15% recurring
        "session_id": f"session_{uuid4().hex[:16]}",
    }


def generate_card_testing_transaction(card_token: Optional[str] = None) -> dict:
    """
    Generate a card testing attack transaction.

    Card testing pattern:
    - Same card used repeatedly
    - Small amounts ($1-$5)
    - Rapid succession
    """
    card = card_token or f"card_test_{uuid4().hex[:8]}"

    return generate_transaction(
        card_token=card,
        amount_cents=random.randint(100, 500),  # Small amounts
        is_new_user=True,  # Often new accounts
    )


def generate_fraud_ring_transaction(device_id: Optional[str] = None) -> dict:
    """
    Generate a fraud ring pattern transaction.

    Fraud ring pattern:
    - Same device
    - Multiple different cards
    - Medium-high amounts
    """
    device = device_id or f"device_ring_{uuid4().hex[:8]}"

    return generate_transaction(
        device_id=device,
        card_token=f"card_{uuid4().hex[:8]}",  # Always different card
        amount_cents=random.randint(5000, 20000),  # $50-$200
    )


def generate_geo_anomaly_transaction() -> dict:
    """
    Generate a geographic anomaly transaction.

    Geo anomaly pattern:
    - VPN or proxy detected
    - Country mismatch with card
    - Datacenter IP
    """
    return generate_transaction(
        is_vpn=True,
        country_code=random.choice(["RU", "CN", "NG", "BR"]),  # High-risk countries
    )


def generate_high_value_new_user_transaction() -> dict:
    """
    Generate a high-value new user transaction.

    Friendly fraud indicator:
    - New account (< 7 days)
    - High value transaction
    - First transaction
    """
    return generate_transaction(
        is_high_value=True,
        is_new_user=True,
    )


# =============================================================================
# BATCH GENERATORS (for data seeding)
# =============================================================================

def generate_batch(count: int, scenario: str = "mixed") -> list:
    """
    Generate a batch of transactions.

    Args:
        count: Number of transactions to generate
        scenario: "mixed" (uses TRAFFIC_MIX), "legitimate", "attack"

    Returns:
        list: List of transaction payloads
    """
    transactions = []

    for _ in range(count):
        if scenario == "legitimate":
            transactions.append(generate_transaction())
        elif scenario == "attack":
            attack_type = random.choice(["card_testing", "fraud_ring", "geo_anomaly"])
            if attack_type == "card_testing":
                transactions.append(generate_card_testing_transaction())
            elif attack_type == "fraud_ring":
                transactions.append(generate_fraud_ring_transaction())
            else:
                transactions.append(generate_geo_anomaly_transaction())
        else:  # mixed
            roll = random.random()
            cumulative = 0
            for scenario_name, probability in TRAFFIC_MIX.items():
                cumulative += probability
                if roll < cumulative:
                    if scenario_name == "legitimate":
                        transactions.append(generate_transaction())
                    elif scenario_name == "card_testing":
                        transactions.append(generate_card_testing_transaction())
                    elif scenario_name == "fraud_ring":
                        transactions.append(generate_fraud_ring_transaction())
                    elif scenario_name == "geo_anomaly":
                        transactions.append(generate_geo_anomaly_transaction())
                    elif scenario_name == "high_value_new_user":
                        transactions.append(generate_high_value_new_user_transaction())
                    break

    return transactions


if __name__ == "__main__":
    # Test data generation
    print("Sample legitimate transaction:")
    print(generate_transaction())
    print()
    print("Sample card testing transaction:")
    print(generate_card_testing_transaction())
    print()
    print("Sample fraud ring transaction:")
    print(generate_fraud_ring_transaction())

"""
Realistic Transaction Data Generator - Telco/MSP Payment Fraud

Generates telco service transactions with realistic distributions for load testing.
Supports various fraud patterns including SIM farms, device resale, and equipment fraud.

Target verticals:
- Mobile (SIM activation, topup, device upgrade, SIM swap, international enable)
- Broadband (service activation, equipment swap, speed upgrade, equipment purchase)
"""

import random
from datetime import datetime, UTC
from uuid import uuid4
from typing import Optional


# =============================================================================
# CONFIGURATION - Telco/MSP Payment Fraud Patterns
# =============================================================================

# Transaction amount distribution (in cents)
# Telco transactions vary by event type
AMOUNT_DISTRIBUTION = [
    ((100, 500), 0.35),        # $1-$5 (small topups, SIM activation fees)
    ((501, 2000), 0.25),       # $5.01-$20.00 (medium topups, service fees)
    ((2001, 10000), 0.20),     # $20.01-$100.00 (large topups, equipment fees)
    ((10001, 50000), 0.12),    # $100.01-$500.00 (device deposits, CPE)
    ((50001, 150000), 0.08),   # $500.01-$1500.00 (subsidized devices)
]

# Entity pool sizes - controls cardinality for velocity patterns
POOL_SIZES = {
    "cards": 10000,
    "devices": 5000,
    "ips": 2000,
    "subscribers": 8000,
    "accounts": 500,  # Service accounts
    "phone_numbers": 15000,
    "imeis": 12000,
    "modems": 3000,
}

# Service types
SERVICE_TYPES = ["mobile", "broadband"]

# Event subtypes with their frequency distributions
MOBILE_EVENT_SUBTYPES = [
    ("sim_activation", 0.30),    # New SIM - SIM farm risk
    ("topup", 0.40),             # Prepaid reload - card testing
    ("device_upgrade", 0.15),   # Subsidized device - resale fraud
    ("sim_swap", 0.10),         # SIM change - account takeover
    ("international_enable", 0.05),  # Roaming - IRSF setup
]

BROADBAND_EVENT_SUBTYPES = [
    ("service_activation", 0.35),  # New service - promo abuse
    ("speed_upgrade", 0.30),       # Tier change - promo abuse
    ("equipment_swap", 0.20),      # Modem change - equipment fraud
    ("equipment_purchase", 0.15),  # CPE buy - resale fraud
]

# High-risk subtypes that warrant additional scrutiny
HIGH_RISK_SUBTYPES = {
    "device_upgrade",
    "sim_swap",
    "international_enable",
    "equipment_purchase",
}

# Traffic mix percentages
TRAFFIC_MIX = {
    "legitimate": 0.95,
    "card_testing": 0.02,      # Rapid SIM activations/topups with same card
    "fraud_ring": 0.01,        # Same device, multiple subscriber accounts
    "geo_anomaly": 0.01,       # Service activation from unexpected location
    "high_value_new_subscriber": 0.01,  # New subscriber, device upgrade
}

# Card brands and their distribution
CARD_BRANDS = [
    ("Visa", 0.50),
    ("Mastercard", 0.30),
    ("Amex", 0.10),
    ("Discover", 0.05),
    ("Other", 0.05),
]

# Device types (for the device making the request, not the product)
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

# Service regions (internal)
SERVICE_REGIONS = ["US", "CA", "MX"]


# =============================================================================
# ENTITY POOLS - Pre-generated for consistent velocity patterns
# =============================================================================

# Initialize pools with deterministic IDs for reproducibility
_card_pool = [f"card_{i:05d}" for i in range(POOL_SIZES["cards"])]
_device_pool = [f"device_{i:05d}" for i in range(POOL_SIZES["devices"])]
_ip_pool = [f"192.168.{i // 256}.{i % 256}" for i in range(POOL_SIZES["ips"])]
_subscriber_pool = [f"subscriber_{i:05d}" for i in range(POOL_SIZES["subscribers"])]
_account_pool = [f"account_{i:03d}" for i in range(POOL_SIZES["accounts"])]

# Telco-specific identifier pools
_phone_pool = [f"1555{i:07d}" for i in range(POOL_SIZES["phone_numbers"])]
_imei_pool = [f"35345678{i:07d}" for i in range(POOL_SIZES["imeis"])]
_sim_pool = [f"8901260{i:013d}" for i in range(15000)]  # SIM ICCID format
_modem_pool = [f"00:1A:2B:{i//256:02X}:{i%256:02X}:00" for i in range(POOL_SIZES["modems"])]
_cpe_pool = [f"CPE-{i:06d}" for i in range(3000)]
_address_pool = [f"addr_hash_{i:05d}" for i in range(5000)]

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


def generate_amount(event_subtype: str = None) -> int:
    """
    Generate realistic transaction amount in cents.
    Amount varies by event subtype in telco context.
    """
    # Event-specific amounts
    if event_subtype == "topup":
        return random.choice([500, 1000, 2000, 2500, 5000])  # $5, $10, $20, $25, $50
    elif event_subtype == "sim_activation":
        return random.randint(0, 3000)  # $0-$30 activation fee
    elif event_subtype == "device_upgrade":
        return random.randint(0, 150000)  # $0-$1500 (subsidized devices)
    elif event_subtype == "equipment_purchase":
        return random.randint(5000, 30000)  # $50-$300 (CPE/modems)
    elif event_subtype == "international_enable":
        return random.randint(0, 5000)  # $0-$50 setup fee
    elif event_subtype == "service_activation":
        return random.randint(0, 10000)  # $0-$100 activation fee
    elif event_subtype == "speed_upgrade":
        return random.randint(0, 5000)  # $0-$50 upgrade fee
    elif event_subtype == "equipment_swap":
        return random.randint(0, 10000)  # $0-$100 swap fee
    else:
        # Generic distribution
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


def get_random_subscriber() -> str:
    """Get a random subscriber from the pool."""
    return random.choice(_subscriber_pool)


def get_random_account() -> str:
    """Get a random service account from the pool."""
    return random.choice(_account_pool)


def get_random_phone() -> str:
    """Get a random phone number from the pool."""
    return random.choice(_phone_pool)


def get_random_imei() -> str:
    """Get a random IMEI from the pool."""
    return random.choice(_imei_pool)


def get_random_sim() -> str:
    """Get a random SIM ICCID from the pool."""
    return random.choice(_sim_pool)


def get_random_modem() -> str:
    """Get a random modem MAC from the pool."""
    return random.choice(_modem_pool)


def get_random_cpe() -> str:
    """Get a random CPE serial from the pool."""
    return random.choice(_cpe_pool)


def get_random_address_hash() -> str:
    """Get a random address hash from the pool."""
    return random.choice(_address_pool)


# =============================================================================
# TRANSACTION GENERATORS
# =============================================================================

def generate_transaction(
    card_token: Optional[str] = None,
    device_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    subscriber_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    service_type: Optional[str] = None,
    event_subtype: Optional[str] = None,
    is_high_value: bool = False,
    is_new_subscriber: bool = False,
    is_vpn: bool = False,
    is_emulator: bool = False,
    country_code: Optional[str] = None,
    phone_number: Optional[str] = None,
    imei: Optional[str] = None,
    sim_iccid: Optional[str] = None,
    modem_mac: Optional[str] = None,
    cpe_serial: Optional[str] = None,
) -> dict:
    """
    Generate a realistic telco service transaction.

    Args:
        card_token: Specific card token (or random from pool)
        device_id: Specific device ID (or random from pool)
        ip_address: Specific IP (or random from pool)
        subscriber_id: Specific subscriber (or random from pool)
        amount_cents: Specific amount (or realistic distribution)
        service_type: "mobile" or "broadband" (or random)
        event_subtype: Specific event (or random based on service_type)
        is_high_value: Force high-value transaction (device upgrade)
        is_new_subscriber: Force new subscriber (low account age)
        is_vpn: Mark as VPN traffic
        is_emulator: Mark as emulator device
        country_code: Specific country (or weighted random)
        phone_number: Mobile phone number (mobile events)
        imei: Device IMEI (mobile events)
        sim_iccid: SIM card ICCID (mobile events)
        modem_mac: Modem MAC address (broadband events)
        cpe_serial: CPE serial number (broadband events)

    Returns:
        dict: Transaction payload ready for /decide endpoint
    """
    transaction_id = uuid4().hex
    idempotency_key = f"idem_{transaction_id}"

    # Use provided values or generate
    card = card_token or get_random_card()
    device = device_id or get_random_device()
    ip = ip_address or get_random_ip()
    subscriber = subscriber_id or get_random_subscriber()

    # Service type and event subtype
    svc_type = service_type or random.choice(SERVICE_TYPES)
    if event_subtype:
        evt_subtype = event_subtype
    else:
        if svc_type == "mobile":
            evt_subtype = weighted_choice(MOBILE_EVENT_SUBTYPES)
        else:
            evt_subtype = weighted_choice(BROADBAND_EVENT_SUBTYPES)

    # Amount based on event type
    if amount_cents:
        amount = amount_cents
    elif is_high_value:
        amount = random.randint(50000, 150000)  # $500-$1500 (device upgrade range)
    else:
        amount = generate_amount(evt_subtype)

    country = country_code or weighted_choice(COUNTRIES)
    device_type = weighted_choice(DEVICE_TYPES)
    os_type = weighted_choice(OS_TYPES)
    card_brand = weighted_choice(CARD_BRANDS)

    # Subscriber age - most are established, some are new
    if is_new_subscriber:
        subscriber_age = random.randint(0, 7)
    else:
        subscriber_age = random.randint(30, 1000)

    # Build the transaction
    txn = {
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
        # Telco-specific fields
        "service_id": get_random_account(),
        "service_name": f"Telco Service {random.randint(1, 100)}",
        "service_type": svc_type,
        "service_region": random.choice(SERVICE_REGIONS),
        "event_subtype": evt_subtype,
        "subscriber_id": subscriber,
        "account_age_days": subscriber_age,
        "is_guest": random.random() < 0.05,  # 5% guest (lower for telco)
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
        "channel": random.choice(["web", "mobile", "store", "call_center"]),
        "is_recurring": evt_subtype == "topup" and random.random() < 0.30,  # 30% of topups are auto-reload
        "session_id": f"session_{uuid4().hex[:16]}",
    }

    # Add telco-specific identifiers based on service type
    if svc_type == "mobile":
        txn["phone_number"] = phone_number or get_random_phone()
        txn["imei"] = imei or get_random_imei()
        txn["sim_iccid"] = sim_iccid or get_random_sim()
    else:  # broadband
        txn["modem_mac"] = modem_mac or get_random_modem()
        txn["cpe_serial"] = cpe_serial or get_random_cpe()
        txn["service_address_hash"] = get_random_address_hash()

    return txn


def generate_sim_farm_transaction(card_token: Optional[str] = None) -> dict:
    """
    Generate a SIM farm attack transaction.

    SIM farm pattern:
    - Same card used for multiple SIM activations
    - Different phone numbers each time
    - Rapid succession from emulator/automated device
    """
    card = card_token or f"card_farm_{uuid4().hex[:8]}"

    return generate_transaction(
        card_token=card,
        service_type="mobile",
        event_subtype="sim_activation",
        phone_number=f"1555{random.randint(1000000, 9999999)}",  # Unique phone each time
        is_emulator=random.random() < 0.3,  # 30% from emulators
    )


def generate_card_testing_transaction(card_token: Optional[str] = None) -> dict:
    """
    Generate a card testing attack transaction.

    Card testing pattern in telco:
    - Same card used repeatedly for small topups
    - Small amounts ($5-$10)
    - Rapid succession
    """
    card = card_token or f"card_test_{uuid4().hex[:8]}"

    return generate_transaction(
        card_token=card,
        service_type="mobile",
        event_subtype="topup",
        amount_cents=random.choice([500, 1000]),  # $5 or $10 topups
        is_new_subscriber=True,
    )


def generate_device_resale_transaction(card_token: Optional[str] = None) -> dict:
    """
    Generate a device resale fraud transaction.

    Device resale pattern:
    - Same card for multiple device upgrades
    - Different IMEIs each time
    - High-value subsidized devices
    """
    card = card_token or f"card_resale_{uuid4().hex[:8]}"

    return generate_transaction(
        card_token=card,
        service_type="mobile",
        event_subtype="device_upgrade",
        imei=f"35345678{random.randint(1000000, 9999999)}",  # Unique IMEI
        is_high_value=True,
        is_new_subscriber=True,
    )


def generate_equipment_fraud_transaction(card_token: Optional[str] = None) -> dict:
    """
    Generate an equipment fraud transaction.

    Equipment fraud pattern:
    - Same card for multiple modem/CPE purchases
    - Different MAC addresses / serials each time
    - Multiple service addresses
    """
    card = card_token or f"card_equip_{uuid4().hex[:8]}"

    return generate_transaction(
        card_token=card,
        service_type="broadband",
        event_subtype="equipment_purchase",
        modem_mac=f"00:1A:2B:{random.randint(0,255):02X}:{random.randint(0,255):02X}:00",
        cpe_serial=f"CPE-{random.randint(100000, 999999)}",
    )


def generate_fraud_ring_transaction(device_id: Optional[str] = None) -> dict:
    """
    Generate a fraud ring pattern transaction.

    Fraud ring pattern:
    - Same device
    - Multiple different cards
    - Multiple subscriber accounts
    """
    device = device_id or f"device_ring_{uuid4().hex[:8]}"

    return generate_transaction(
        device_id=device,
        card_token=f"card_{uuid4().hex[:8]}",  # Always different card
        subscriber_id=f"subscriber_ring_{uuid4().hex[:8]}",  # Different subscriber
        service_type="mobile",
        event_subtype="sim_activation",
    )


def generate_geo_anomaly_transaction() -> dict:
    """
    Generate a geographic anomaly transaction.

    Geo anomaly pattern:
    - VPN or proxy detected
    - Country mismatch with card
    - Datacenter IP (automated)
    """
    return generate_transaction(
        is_vpn=True,
        country_code=random.choice(["RU", "CN", "NG", "BR"]),  # High-risk countries
        service_type="mobile",
        event_subtype=random.choice(["sim_activation", "international_enable"]),
    )


def generate_high_value_new_subscriber_transaction() -> dict:
    """
    Generate a high-value new subscriber transaction.

    Friendly fraud indicator in telco:
    - New subscriber (< 7 days)
    - Device upgrade (subsidized phone)
    - High value
    """
    return generate_transaction(
        service_type="mobile",
        event_subtype="device_upgrade",
        is_high_value=True,
        is_new_subscriber=True,
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
            attack_type = random.choice([
                "card_testing",
                "sim_farm",
                "device_resale",
                "equipment_fraud",
                "fraud_ring",
                "geo_anomaly",
            ])
            if attack_type == "card_testing":
                transactions.append(generate_card_testing_transaction())
            elif attack_type == "sim_farm":
                transactions.append(generate_sim_farm_transaction())
            elif attack_type == "device_resale":
                transactions.append(generate_device_resale_transaction())
            elif attack_type == "equipment_fraud":
                transactions.append(generate_equipment_fraud_transaction())
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
                    elif scenario_name == "high_value_new_subscriber":
                        transactions.append(generate_high_value_new_subscriber_transaction())
                    break

    return transactions


if __name__ == "__main__":
    # Test data generation
    print("=" * 60)
    print("Telco/MSP Payment Fraud - Sample Transactions")
    print("=" * 60)

    print("\n1. Legitimate mobile transaction (SIM activation):")
    print(generate_transaction(service_type="mobile", event_subtype="sim_activation"))

    print("\n2. Legitimate broadband transaction (service activation):")
    print(generate_transaction(service_type="broadband", event_subtype="service_activation"))

    print("\n3. SIM farm attack transaction:")
    print(generate_sim_farm_transaction())

    print("\n4. Card testing transaction (topup):")
    print(generate_card_testing_transaction())

    print("\n5. Device resale fraud transaction:")
    print(generate_device_resale_transaction())

    print("\n6. Equipment fraud transaction:")
    print(generate_equipment_fraud_transaction())

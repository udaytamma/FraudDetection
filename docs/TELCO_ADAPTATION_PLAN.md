# Telco/MSP Adaptation Plan

> This document captures the complete plan for adapting the FraudDetection platform from generic e-commerce to Telco/MSP Payment Fraud detection.

## Overview

| Aspect | Decision |
|--------|----------|
| **Target Domain** | Telco/MSP Payment Fraud |
| **Verticals** | Mobile + Broadband (skip TV) |
| **Identifiers** | Representative subset (6-8 per vertical) |
| **Events** | High-fraud-risk only (5-6 per vertical) |
| **Architecture** | Unchanged |
| **Detection Logic** | Unchanged (rename fields only) |

---

## Phase 1: Schema Changes

### 1.1 Event Schema (`src/schemas/events.py`)

| Action | Current | New |
|--------|---------|-----|
| Rename | `merchant_id` | `service_id` |
| Rename | `merchant_name` | `service_name` |
| Remove | `merchant_mcc` | - |
| Rename | `merchant_country` | `service_region` |
| Add | - | `service_type: str` (mobile \| broadband) |
| Add | - | `event_subtype: str` |
| Add | - | `subscriber_id: Optional[str]` |
| Add | - | `phone_number: Optional[str]` (mobile) |
| Add | - | `imei: Optional[str]` (mobile) |
| Add | - | `sim_iccid: Optional[str]` (mobile) |
| Add | - | `modem_mac: Optional[str]` (broadband) |
| Add | - | `cpe_serial: Optional[str]` (broadband) |
| Add | - | `service_address_hash: Optional[str]` (broadband) |

**Event Subtypes (high-fraud-risk only):**

```python
# Mobile
"sim_activation"       # New SIM - SIM farm risk
"sim_swap"             # SIM change - account takeover
"device_upgrade"       # Subsidized device - resale fraud
"topup"                # Prepaid reload - stolen card testing
"international_enable" # Roaming - IRSF setup

# Broadband
"service_activation"   # New service - promo abuse
"equipment_swap"       # Modem change - equipment fraud
"speed_upgrade"        # Tier change - promo abuse
"equipment_purchase"   # CPE buy - resale fraud
```

### 1.2 Feature Schema (`src/schemas/features.py`)

**VelocityFeatures - Rename:**

| Current | New |
|---------|-----|
| `card_distinct_merchants_24h` | `card_distinct_accounts_24h` |

**VelocityFeatures - Add:**

```python
# Mobile-specific
card_distinct_phone_numbers_24h: int   # SIM farm detection
card_distinct_imeis_24h: int           # Device resale fraud
imei_distinct_sims_7d: int             # Device cloning
phone_sim_swaps_30d: int               # Account takeover

# Broadband-specific
card_distinct_modems_30d: int          # Equipment fraud
address_distinct_accounts_30d: int     # Promo stacking
```

**EntityFeatures - Rename:**

| Current | New |
|---------|-----|
| `merchant_is_high_risk_mcc` | `service_is_high_risk` |
| `merchant_chargeback_rate_30d` | `service_chargeback_rate_30d` |

**EntityFeatures - Add:**

```python
# Subscriber context
subscriber_age_days: Optional[int]
subscriber_is_new: bool
subscriber_total_services: int         # How many services they have
```

---

## Phase 2: Detection Updates

### 2.1 Detector Docstrings (comments only, no logic changes)

| File | Changes |
|------|---------|
| `card_testing.py` | Update docstrings: "checkout" → "service activation", "merchant" → "account" |
| `velocity.py` | Update docstrings: "merchant" → "subscriber account" |
| `detector.py` | No changes |
| `geo.py` | No changes |
| `bot.py` | No changes |

### 2.2 Card Testing Detector - Threshold Comments

Update rationale comments to reflect telco context:

```python
# Before: "Exceeds any legitimate checkout behavior"
# After:  "Exceeds any legitimate service activation behavior"
```

---

## Phase 3: Scoring Updates

### 3.1 Risk Scorer (`src/scoring/risk_scorer.py`)

- No logic changes
- Update comments referencing "merchant" to "service/account"

### 3.2 Friendly Fraud Scorer (`src/scoring/friendly_fraud.py`)

- Update references from "merchant" to "subscriber account"
- Update high-value threshold context (device purchase vs generic purchase)

---

## Phase 4: Policy Updates

### 4.1 Policy Config (`config/policy.yaml`)

Update rule descriptions:

```yaml
# Before
- id: high_risk_merchant
  description: "Transaction at high-risk merchant category"

# After
- id: high_risk_service
  description: "High-risk service type (device upgrade, international enable)"
```

---

## Phase 5: Load Testing Updates

### 5.1 Data Generator (`loadtest/data_generator.py`)

**Remove:**
```python
MERCHANT_MCCS = [...]
HIGH_RISK_MCCS = [...]
```

**Add:**
```python
SERVICE_TYPES = ["mobile", "broadband"]

MOBILE_EVENT_SUBTYPES = [
    ("sim_activation", 0.30),
    ("topup", 0.40),
    ("device_upgrade", 0.15),
    ("sim_swap", 0.10),
    ("international_enable", 0.05),
]

BROADBAND_EVENT_SUBTYPES = [
    ("service_activation", 0.35),
    ("speed_upgrade", 0.30),
    ("equipment_swap", 0.20),
    ("equipment_purchase", 0.15),
]

HIGH_RISK_SUBTYPES = {"device_upgrade", "sim_swap", "international_enable", "equipment_purchase"}
```

**Update `generate_transaction()`:**
- Replace merchant fields with service fields
- Add telco-specific identifiers based on service_type
- Generate realistic phone numbers, IMEIs, MAC addresses

**Update `TRAFFIC_MIX` descriptions:**
```python
TRAFFIC_MIX = {
    "legitimate": 0.95,
    "card_testing": 0.02,      # Rapid SIM activations with same card
    "fraud_ring": 0.01,        # Same device, multiple subscriber accounts
    "geo_anomaly": 0.01,       # Service activation from unexpected location
    "high_value_new_user": 0.01,  # New subscriber, device upgrade
}
```

**Add fraud pattern generators:**
```python
def generate_sim_farm_transaction()      # Same card, different phone numbers
def generate_equipment_fraud_transaction() # Same card, different modems
```

### 5.2 Locust File (`loadtest/locustfile.py`)

- Update scenario descriptions in docstrings
- No logic changes needed

---

## Phase 6: Test Updates

### 6.1 Test Files

| File | Changes |
|------|---------|
| `tests/conftest.py` | Update fixtures with new field names |
| `tests/test_schemas.py` | Update field references |
| `tests/test_detection.py` | Update test data with telco fields |
| `tests/test_api.py` | Update request payloads |
| `tests/test_policy.py` | Update rule references |

### 6.2 Test Data Updates

Replace:
```python
"merchant_id": "merchant_001"
"merchant_mcc": "5411"
```

With:
```python
"service_id": "mobile_prepaid_001"
"service_type": "mobile"
"event_subtype": "sim_activation"
"phone_number": "15551234567"
"imei": "353456789012345"
```

---

## Phase 7: Documentation Updates

### 7.1 ProjectDocs - Fraud Platform Docs

| File | Changes |
|------|---------|
| `docs/fraud-platform/01-overview.md` | Update intro to mention Telco/MSP Payment Fraud focus |
| `docs/fraud-platform/02-architecture.md` | Update entity examples |
| `docs/fraud-platform/03-data-model.md` | Update schema documentation |
| `docs/fraud-platform/04-detection.md` | Update fraud pattern descriptions |
| `docs/fraud-platform/05-api-reference.md` | Update request/response examples |

### 7.2 Nebula Thinking Docs

| File | Changes |
|------|---------|
| `fraud-detection-thinking/` pages | Update examples to telco context |
| Data points reference | Update feature rationale for telco |

### 7.3 Blog Post

Minimal changes - already generic enough. May add one line:
> "While this implementation targets Telco/MSP Payment Fraud patterns, the architecture is domain-agnostic."

---

## Phase 8: Dashboard Updates

### 8.1 Streamlit Dashboard (`dashboard.py`)

- Update chart labels: "Merchant" → "Service Type"
- Update dropdown options with service types
- Update sample data generation

---

## Implementation Order

```
Phase 1: Schema Changes (Foundation)
    └── events.py, features.py, decisions.py

Phase 2: Detection Updates
    └── card_testing.py, velocity.py (docstrings only)

Phase 3: Scoring Updates
    └── risk_scorer.py, friendly_fraud.py (comments only)

Phase 4: Policy Updates
    └── policy.yaml

Phase 5: Load Testing Updates
    └── data_generator.py, locustfile.py

Phase 6: Test Updates
    └── conftest.py, test_*.py

Phase 7: Documentation Updates
    └── ProjectDocs/docs/fraud-platform/*.md, Nebula pages

Phase 8: Dashboard Updates
    └── dashboard.py
```

---

## File Change Summary

| Category | Files | Estimated Changes |
|----------|-------|-------------------|
| Schema | 3 | ~100 lines add/modify |
| Detection | 2 | ~20 lines (comments) |
| Scoring | 2 | ~10 lines (comments) |
| Policy | 1 | ~15 lines |
| Load Test | 2 | ~150 lines |
| Tests | 5 | ~100 lines |
| Docs | 6-8 | ~200 lines |
| Dashboard | 1 | ~30 lines |
| **Total** | **~22 files** | **~625 lines** |

---

## Validation Checklist

After implementation:

- [ ] `pytest tests/ -v` passes
- [ ] `python -m py_compile src/**/*.py` no syntax errors
- [ ] `uvicorn src.api.main:app` starts without error
- [ ] `/decide` endpoint accepts new schema
- [ ] `locust -f loadtest/locustfile.py` runs without error
- [ ] `streamlit run dashboard.py` displays correctly
- [ ] `npm run build` in ProjectDocs succeeds

---

## Interview Positioning

> "I built this as a Telco/MSP Payment Fraud platform, but the architecture is domain-agnostic. The same velocity-based detection, policy engine, and scoring approach works for e-commerce or fintech - you just swap the features. For telco, I track subscriber accounts and SIM activations instead of merchants and cart checkouts."

This demonstrates:
1. Domain knowledge (features are telco-correct)
2. System design skills (architecture transfers)
3. Abstraction ability (senior-level thinking)

---

*Generated: 2026-01-04*

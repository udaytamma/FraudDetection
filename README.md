# Fraud Detection Platform

Real-time payment fraud detection for Telco/MSP payment processing. Velocity-based rules, configurable policy engine, and comprehensive observability.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7.0-dc382d.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Overview

A production-grade fraud detection platform designed for payment processing systems. Features real-time decisioning with sub-100ms latency, configurable policy engine, and evidence capture for dispute resolution.

## Features

### Detection Capabilities
- **Card Testing Attack Detection** - Identifies rapid small-value transactions
- **Velocity-Based Rules** - Configurable thresholds for transaction frequency
- **Geographic Anomaly Detection** - Flags impossible travel scenarios
- **Bot/Emulator Detection** - Device fingerprint analysis
- **Friendly Fraud Scoring** - Profile-based friendly fraud risk scoring

### Architecture
- **Real-Time Decisioning** - Sub-100ms response times
- **Hot-Reload Policy Engine** - Update rules without restart
- **Evidence Capture** - Full transaction context for disputes
- **Prometheus Metrics** - Production-grade observability

### API
- **RESTful Endpoints** - OpenAPI documented
- **Async Processing** - Non-blocking I/O
- **Request Validation** - Pydantic models

## Tech Stack

| Layer | Technology |
|-------|------------|
| **API** | FastAPI |
| **Velocity Store** | Redis (sorted sets) |
| **Evidence Store** | PostgreSQL |
| **Monitoring** | Prometheus + Grafana |
| **Dashboard** | Streamlit |

## Quick Start

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- Redis 7.0+
- PostgreSQL 15+

### Installation

```bash
# Clone repository
git clone https://github.com/udaytamma/FraudDetection.git
cd FraudDetection

# Start infrastructure
docker-compose up -d

# Setup Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Initialize database
psql -f scripts/init_db.sql

# Start API server
uvicorn src.api.main:app --reload --port 8000
```

### Running the Dashboard

```bash
# In a separate terminal (foreground)
streamlit run dashboard.py --server.port 8501

# For background/headless mode (required for scripts/CI)
streamlit run dashboard.py --server.port 8501 --server.headless true
```

Open [http://localhost:8501](http://localhost:8501) for the demo dashboard.

### Running Load Tests

```bash
# Start Locust web UI
cd loadtest && locust -f locustfile.py --host=http://localhost:8000 --web-port=8089
```

Open [http://localhost:8089](http://localhost:8089) for the load testing dashboard.

## Authentication & RBAC

The API uses a three-tier token authentication system. All tokens are optional—if not configured, endpoints are open.

### Token Types

| Token | Environment Variable | Purpose |
|-------|---------------------|---------|
| API Token | `API_TOKEN` | Standard API access (`/decide`, policy reads) |
| Admin Token | `ADMIN_TOKEN` | Policy mutation (`/policy/reload`) |
| Metrics Token | `METRICS_TOKEN` | Observability endpoints (`/metrics`, `/metrics/summary`) |

### Endpoint Protection Matrix

| Endpoint | Required Token | Description |
|----------|---------------|-------------|
| `POST /decide` | API_TOKEN | Make fraud decisions |
| `POST /chargebacks` | API_TOKEN | Ingest chargeback notifications |
| `GET /policy/*` | API_TOKEN | Read policy configuration |
| `PUT/POST /policy/*` | ADMIN_TOKEN | Mutate policy (thresholds, rules) |
| `GET /metrics` | METRICS_TOKEN | Prometheus metrics |
| `GET /metrics/summary` | METRICS_TOKEN | Telemetry summary |
| `GET /health` | None | Health check (always open) |

### Authentication Headers

Both header formats are supported:

```bash
# Bearer token (recommended)
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/decide

# API key header
curl -H "X-API-Key: $API_TOKEN" http://localhost:8000/decide
```

### Generating Tokens

```bash
# Generate a secure random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Safe Mode

Safe Mode is a kill switch that bypasses normal fraud decisioning. Use it during incidents, deployments, or when the fraud system itself is misbehaving.

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SAFE_MODE_ENABLED` | Enable/disable safe mode | `false` |
| `SAFE_MODE_DECISION` | Decision to return when enabled | `ALLOW` |

### Behavior

When `SAFE_MODE_ENABLED=true`:
- All `/decide` requests return the configured `SAFE_MODE_DECISION`
- Scoring, velocity updates, and feature computation are skipped
- Evidence is captured with zeroed scores for auditability
- Prometheus decision metrics and latency are recorded

**Use cases:**
- Emergency bypass during false positive spikes
- Testing payment flow without fraud interference
- Graceful degradation when dependencies fail

---

## API Reference

### Decision Endpoint

```bash
POST /decide
Authorization: Bearer $API_TOKEN
Content-Type: application/json

{
  "transaction_id": "txn_123",
  "amount": 99.99,
  "currency": "USD",
  "card_hash": "abc123...",
  "merchant_id": "merch_456",
  "device_fingerprint": "fp_789",
  "ip_address": "192.168.1.1",
  "timestamp": "2026-01-12T19:00:00Z"
}
```

**Response:**
```json
{
  "decision": "APPROVE",
  "risk_score": 23,
  "signals": [],
  "evidence_id": "ev_abc123",
  "latency_ms": 45
}
```

### All Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/decide` | API_TOKEN | Make fraud decision |
| POST | `/chargebacks` | API_TOKEN | Ingest chargeback notification |
| GET | `/metrics` | METRICS_TOKEN | Prometheus metrics |
| GET | `/metrics/summary` | METRICS_TOKEN | Recent telemetry for dashboards |
| GET | `/policy` | API_TOKEN | Active policy configuration |
| GET | `/policy/version` | API_TOKEN | Current policy version and hash |
| GET | `/policy/versions` | API_TOKEN | Version history |
| GET | `/policy/versions/{version}` | API_TOKEN | Specific version details |
| POST | `/policy/reload` | ADMIN_TOKEN | Hot-reload policy from YAML |
| PUT | `/policy/thresholds` | ADMIN_TOKEN | Update score thresholds |
| POST | `/policy/rules` | ADMIN_TOKEN | Add policy rule |
| PUT | `/policy/rules/{rule_id}` | ADMIN_TOKEN | Update policy rule |
| DELETE | `/policy/rules/{rule_id}` | ADMIN_TOKEN | Delete policy rule |
| POST | `/policy/lists/{list_type}` | None | Add to blocklist/allowlist |
| DELETE | `/policy/lists/{list_type}/{value}` | None | Remove from list |
| POST | `/policy/rollback/{target_version}` | None | Rollback to previous version |
| GET | `/policy/diff/{version1}/{version2}` | None | Compare two policy versions |

## Project Structure

```
FraudDetection/
├── src/
│   ├── api/                    # FastAPI application
│   │   └── main.py             # API routes and middleware
│   ├── config/                 # Settings management
│   │   └── settings.py         # Pydantic settings
│   ├── schemas/                # Data models
│   │   ├── request.py          # API request models
│   │   └── response.py         # API response models
│   ├── features/               # Feature extraction
│   │   └── velocity.py         # Velocity counter logic
│   ├── detection/              # Fraud detectors
│   │   ├── card_testing.py     # Card testing detection
│   │   ├── velocity.py         # Velocity rules
│   │   └── geo_anomaly.py      # Geographic checks
│   ├── scoring/                # Risk scoring
│   │   └── scorer.py           # Score aggregation
│   ├── policy/                 # Policy engine
│   │   └── engine.py           # Rule evaluation
│   ├── evidence/               # Evidence capture
│   │   └── capture.py          # Transaction context
│   └── metrics/                # Observability
│       └── prometheus.py       # Metric definitions
├── config/
│   ├── policy.yaml             # Policy configuration
│   └── prometheus.yml          # Prometheus config
├── scripts/
│   └── init_db.sql             # Database schema
├── tests/                      # Test suite
├── dashboard.py                # Streamlit dashboard
├── docker-compose.yml          # Infrastructure
└── requirements.txt
```

## Configuration

### Policy Configuration

Edit `config/policy.yaml`:

```yaml
version: 1.0.0
default_action: ALLOW

thresholds:
  risk:
    score_type: risk
    block_threshold: 0.85
    review_threshold: 0.6
    friction_threshold: 0.35
  criminal:
    score_type: criminal
    block_threshold: 0.85
    review_threshold: 0.65
    friction_threshold: 0.4

rules:
  - id: emulator_block
    name: Emulator Block
    enabled: true
    priority: 10
    conditions:
      device_is_emulator: true
    action: BLOCK
  - id: high_value_new_account
    name: High Value New Account
    enabled: true
    priority: 50
    conditions:
      user_is_new: true
      amount_cents_gte: 100000
    action: FRICTION
    friction_type: 3DS
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | PostgreSQL connection pieces | (see `.env.example`) |
| `REDIS_HOST/PORT/DB` | Redis connection pieces | (see `.env.example`) |
| `API_TOKEN` | Token for `/decide` and policy reads | optional |
| `ADMIN_TOKEN` | Token for policy mutation | optional |
| `METRICS_TOKEN` | Token for `/metrics` and `/metrics/summary` | optional |
| `SAFE_MODE_ENABLED` | Bypass decisioning | `false` |
| `SAFE_MODE_DECISION` | ALLOW/BLOCK/REVIEW | `ALLOW` |
| `EVIDENCE_VAULT_KEY` | Encryption key for vault | required for vault |
| `EVIDENCE_HASH_KEY` | HMAC key for identifiers | required for hashing |
| `EVIDENCE_RETENTION_DAYS` | Vault retention | `730` |

## Evidence Vault

The Evidence Vault provides encrypted storage for transaction evidence, supporting PCI/PII compliance and chargeback dispute resolution.

### Architecture

| Table | Purpose | Data |
|-------|---------|------|
| `transaction_evidence` | Primary evidence | HMAC-hashed identifiers, scores, decisions |
| `evidence_vault` | Sensitive data | Fernet-encrypted raw identifiers |

### Key Generation

```bash
# Generate Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate HMAC hash key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `EVIDENCE_VAULT_KEY` | Fernet encryption key | Yes (for vault) |
| `EVIDENCE_HASH_KEY` | HMAC key for hashing | Yes (for hashing) |
| `EVIDENCE_RETENTION_DAYS` | Days to retain evidence | Default: 730 |

### Compliance Notes

- Raw device IDs, IPs, and fingerprints are encrypted at rest
- Primary evidence uses HMAC hashes for analytics without exposing raw values
- Retention is enforced via scheduled purge script (`scripts/purge_evidence_vault.py`)
- This is a PCI-aware design, not a claim of PCI DSS certification

---

## Detection Logic

### Card Testing Detection

Identifies rapid card testing and BIN attacks using 10-minute sliding windows:

```
IF card_attempts_10m >= threshold
OR decline_rate_10m >= ratio_threshold
OR (small_amount + high_velocity pattern)
OR device_distinct_cards_1h >= 5  (BIN attack)
OR ip_distinct_cards_1h >= 10
THEN signal: CARD_TESTING
```

### Velocity Rules

Redis ZSET sliding-window counters tracked per entity:

```
Card:    attempts (10m/1h/24h), declines (10m/1h),
         distinct merchants/devices/IPs (24h)
Device:  attempts (1h/24h), distinct cards (1h/24h),
         distinct users (24h)
IP:      attempts (1h/24h), distinct cards (1h/24h)
User:    transactions (24h/7d), distinct cards (30d),
         amount (24h)
Service: transactions (24h)
```

### Risk Scoring

Weighted signal aggregation:

| Signal | Weight |
|--------|--------|
| Card Testing | 40 |
| Velocity Breach | 30 |
| Geo Anomaly | 25 |
| High Amount | 15 |
| New Device | 10 |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_card_testing.py -v
```

## Monitoring

### Prometheus Metrics

Available at `/metrics` (token required if set):

- `fraud_decisions_total` - Decision counts by outcome
- `fraud_e2e_latency_ms` - Decision latency histogram
- `fraud_signals_total` - Signal trigger counts
- `fraud_policy_version` - Current policy version

### Grafana Dashboard

Import `grafana/fraud-overview.json` for pre-built visualizations (optional).

## Security Considerations

### Capstone Scope Limitations

This is a capstone project demonstrating fraud detection architecture. The following are documented as accepted limitations for production deployment:

| Area | Limitation | Production Recommendation |
|------|-----------|--------------------------|
| Token Comparison | Direct string comparison (timing attack vulnerable) | Use `secrets.compare_digest()` |
| Audit Logging | Auth attempts not logged | Add authentication audit trail |
| Token Rotation | No rotation mechanism | Implement token refresh/rotation |
| Per-User Identity | Shared tokens, no individual audit | Integrate with identity provider |
| Key Rotation | Static encryption keys | Implement key rotation with versioning |

### What IS Implemented

- Three-tier RBAC with separate tokens for API, Admin, and Metrics access
- Fernet encryption for sensitive evidence data
- HMAC hashing for identifier privacy in analytics
- Idempotency enforcement (Redis primary + PostgreSQL fallback)
- Safe mode kill switch for emergency bypass

---

## Documentation

- **Executive Overview**: [`docs/01-Executive-Overview.md`](docs/01-Executive-Overview.md)
- **Execution Strategy**: [`docs/02-Principal-TPM-Execution-Strategy.md`](docs/02-Principal-TPM-Execution-Strategy.md)
- **AI/ML Roadmap**: [`docs/03-AI-ML-Roadmap.md`](docs/03-AI-ML-Roadmap.md)
- **Results & Limitations**: [`docs/04-Results-Personas-Limitations.md`](docs/04-Results-Personas-Limitations.md)
- **Architecture Decisions**: [`docs/architecture-decisions.md`](docs/architecture-decisions.md)
- **Full Reference**: [`FRAUD_DETECTION.md`](FRAUD_DETECTION.md)

## Roadmap

- [ ] ML model integration (XGBoost)
- [ ] Real-time model serving
- [ ] A/B testing framework
- [ ] Case management UI
- [ ] Chargeback feedback loop

## License

This project is licensed under the MIT License.

## Author

**Uday Tamma**
- Portfolio: [zeroleaf.dev](https://zeroleaf.dev)
- GitHub: [@udaytamma](https://github.com/udaytamma)

## Acknowledgments

- Built as a Principal TPM capstone project
- Inspired by production fraud systems at scale

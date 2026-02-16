# Fraud Detection Platform

Real-time payment fraud detection for Telco/MSP payment processing. Velocity-based rules, configurable policy engine, and comprehensive observability.

[![Tests](https://github.com/udaytamma/FraudDetection/actions/workflows/test.yml/badge.svg)](https://github.com/udaytamma/FraudDetection/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7.0-dc382d.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Overview

A production-grade fraud detection platform designed for payment processing systems. Features real-time decisioning with P99 106ms at 50 concurrent users (baseline), configurable policy engine, and evidence capture for dispute resolution.

## Features

### Detection Capabilities
- **Card Testing Attack Detection** - Identifies rapid small-value transactions
- **Velocity-Based Rules** - Configurable thresholds for transaction frequency
- **Geographic Anomaly Detection** - Flags impossible travel scenarios
- **Bot/Emulator Detection** - Device fingerprint analysis
- **Friendly Fraud Scoring** - Profile-based friendly fraud risk scoring

### Architecture
- **Real-Time Decisioning** - P99 106ms at 50 concurrent users (single-worker baseline)
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

The API uses a three-tier token authentication system. Tokens are optional for local development, but **required in production**.
When `APP_ENV=production`, the service will refuse to start unless `API_TOKEN`, `ADMIN_TOKEN`, and `METRICS_TOKEN` are set.

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
| `POST /refunds` | API_TOKEN | Ingest refund notifications |
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

### Public Demo / Production Requirements

For a public demo (or any production-like deployment), set **all** of the following:

```bash
APP_ENV=production
API_TOKEN=...
ADMIN_TOKEN=...
METRICS_TOKEN=...
EVIDENCE_VAULT_KEY=...
EVIDENCE_HASH_KEY=...
```

If any are missing, startup will fail by design.

**Why fail-closed?** The validator runs at Settings construction (startup), not at request time. If a key is missing, the container crashes immediately on deploy -- catching misconfiguration during deployment, not during a customer request at 2am. This follows the same pattern Stripe and AWS use for secret validation.

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
  "idempotency_key": "idem_456",
  "amount_cents": 9900,
  "currency": "USD",
  "card_token": "card_abc123",
  "service_id": "mobile_prepaid_001",
  "service_name": "Telco Mobile Prepaid",
  "service_type": "mobile",
  "event_subtype": "sim_activation",
  "user_id": "user_789",
  "device": {
    "device_id": "dev_456",
    "device_type": "mobile",
    "os": "iOS",
    "os_version": "17.0"
  },
  "geo": {
    "ip_address": "192.168.1.1",
    "country_code": "US",
    "region": "CA",
    "city": "San Francisco"
  }
}
```

**Response:**
```json
{
  "transaction_id": "txn_123",
  "idempotency_key": "idem_456",
  "decision": "ALLOW",
  "scores": {
    "risk_score": 0.12,
    "criminal_score": 0.05,
    "friendly_fraud_score": 0.02,
    "confidence": 0.68
  },
  "reasons": [],
  "processing_time_ms": 45.2,
  "policy_version": "1.0.0",
  "is_cached": false
}
```

### All Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/decide` | API_TOKEN | Make fraud decision |
| POST | `/chargebacks` | API_TOKEN | Ingest chargeback notification |
| POST | `/refunds` | API_TOKEN | Ingest refund notification |
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
| POST | `/policy/lists/{list_type}` | ADMIN_TOKEN | Add to blocklist/allowlist |
| DELETE | `/policy/lists/{list_type}/{value}` | ADMIN_TOKEN | Remove from list |
| POST | `/policy/rollback/{target_version}` | ADMIN_TOKEN | Rollback to previous version |
| GET | `/policy/diff/{version1}/{version2}` | API_TOKEN | Compare two policy versions |

## Project Structure

```
FraudDetection/
├── src/
│   ├── api/                    # FastAPI application
│   │   └── main.py             # API routes and middleware
│   ├── config/                 # Settings management
│   │   └── settings.py         # Pydantic settings
│   ├── schemas/                # Data models
│   │   ├── decisions.py        # Decisions and responses
│   │   ├── entities.py         # Entity profiles
│   │   ├── events.py           # Request/event models
│   │   └── features.py         # Feature schemas
│   ├── features/               # Feature extraction
│   │   ├── store.py            # Feature store orchestration
│   │   └── velocity.py         # Velocity counter logic
│   ├── detection/              # Fraud detectors
│   │   ├── card_testing.py     # Card testing detection
│   │   ├── velocity.py         # Velocity rules
│   │   ├── geo.py              # Geographic anomaly checks
│   │   ├── bot.py              # Bot/emulator detection
│   │   ├── friendly_fraud.py   # Friendly fraud detector
│   │   └── detector.py         # Detection engine orchestration
│   ├── scoring/                # Risk scoring
│   │   ├── risk_scorer.py      # Risk score aggregation
│   │   └── friendly_fraud.py   # Friendly fraud scoring
│   ├── ml/                     # ML scoring + features (Phase 2)
│   │   ├── features.py         # Feature vectorization
│   │   ├── drift.py            # PSI drift detection
│   │   ├── monitoring.py       # Model monitoring helpers
│   │   ├── registry.py         # Model registry
│   │   ├── replay.py           # Offline replay framework
│   │   └── scorer.py           # ML scorer + routing
│   ├── policy/                 # Policy engine
│   │   └── engine.py           # Rule evaluation
│   ├── evidence/               # Evidence capture
│   │   └── service.py          # Evidence service
│   ├── metrics/                # Observability
│   │   └── prometheus.py       # Metric definitions
│   └── utils/                  # Logging utilities
│       └── logger.py           # Structured logging
├── config/
│   ├── policy.yaml             # Policy configuration
│   └── prometheus.yml          # Prometheus config
├── scripts/
│   ├── init_db.sql             # Database schema
│   ├── replay_analysis.py      # Offline replay CLI
│   ├── retrain.sh              # Weekly retrain wrapper
│   ├── seed_synthetic.py       # Synthetic data seeding
│   └── train_model.py          # Phase 2 training pipeline
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

### Policy Architecture

The platform uses a two-tier policy system:

- **Production Policy** (`config/policy.yaml`): 6 rules with tuned thresholds, hot-reloadable without restart
- **Fallback Policy** (`src/policy/rules.py` DEFAULT_POLICY): 3 rules with conservative thresholds, compiled into the application
- **Hot Reload**: `POST /policy/reload` reloads the YAML policy without restarting the API

The fallback policy activates when the YAML file is missing or invalid, ensuring the system remains operational with conservative defaults. The fallback uses higher block thresholds and fewer rules to minimize false positives.

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
| `ML_ENABLED` | Enable ML scoring (Phase 2) | `false` |
| `ML_REGISTRY_PATH` | Path to model registry JSON | `models/registry.json` |
| `ML_CHALLENGER_PERCENT` | Challenger routing percent | `15` |
| `ML_HOLDOUT_PERCENT` | Holdout routing percent | `5` |
| `ML_WEIGHT` | ML weight in ensemble | `0.7` |
| `EVIDENCE_VAULT_KEY` | Encryption key for vault | required for vault |
| `EVIDENCE_HASH_KEY` | HMAC key for identifiers | required for hashing |
| `EVIDENCE_RETENTION_DAYS` | Vault retention | `730` |

**ML scoring note:**
- Run `scripts/train_model.py` to populate `models/registry.json` (champion/challenger).
- Run `scripts/replay_analysis.py` to simulate threshold/model changes on historical evidence.
- Use `scripts/retrain.sh` for the weekly retrain wrapper with AUC gating.
  - Override the gate via `MIN_AUC=0.87` or pass `--min-auc` through.
- Set `ML_ENABLED=true` to activate ML scoring in the API.

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
- Retention enforcement via `scripts/purge_evidence_vault.py` (run as a scheduled task in production)
- This is a PCI-aware design, not a claim of PCI DSS certification

### Evidence Retention

Evidence records are purged after the retention period expires (default 730 days). Run the purge script as a scheduled task:

```bash
python scripts/purge_evidence_vault.py
```

---

## Policy Management API

Dynamic policy configuration without deployment. All mutation endpoints require admin token.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/policy` | GET | View current policy |
| `/policy/version` | GET | Current policy version |
| `/policy/reload` | POST | Hot-reload policy from YAML |
| `/policy/versions` | GET | List all policy versions |
| `/policy/versions/{version}` | GET | Get specific version |
| `/policy/thresholds` | PUT | Update score thresholds |
| `/policy/rules` | POST | Add new detection rule |
| `/policy/rules/{rule_id}` | PUT | Update existing rule |
| `/policy/rules/{rule_id}` | DELETE | Delete rule |
| `/policy/lists/{list_type}` | POST | Add to blocklist/allowlist |
| `/policy/lists/{list_type}/{value}` | DELETE | Remove from list |
| `/policy/rollback/{target_version}` | POST | Rollback to previous version |
| `/policy/diff/{version1}/{version2}` | GET | Compare two versions |

## Data Pipeline

### Chargeback and Refund Ingestion

Ground truth labels for ML training and evidence enrichment:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chargebacks` | POST | Ingest chargeback (marks transaction as confirmed fraud) |
| `/refunds` | POST | Ingest refund (friendly fraud signal) |

These endpoints update evidence vault records with outcome labels used by the ML training pipeline.

### Synthetic Data Seeding

Generate test transactions for development and ML training:

```bash
# Generate synthetic transactions via the API
python scripts/seed_synthetic.py \
  --count 1000 --fraud-ratio 0.15 \
  --api-url http://localhost:8000

# Backdate for historical training data
python scripts/seed_synthetic.py \
  --count 5000 --backdate-captured-at \
  --postgres-url postgresql://user:pass@localhost/fraud
```

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
         distinct accounts/devices/IPs (24h)
Device:  attempts (1h/24h), distinct cards (1h/24h),
         distinct users (24h)
IP:      attempts (1h/24h), distinct cards (1h/24h)
User:    transactions (24h/7d), distinct cards (30d),
         amount (24h)
Service: transactions (24h)
```

### Risk Scoring

Risk scoring is rule-based in the MVP and uses a weighted max for criminal signals plus a friendly fraud score:

| Signal | Weight (weighted max) |
|--------|------------------------|
| Card Testing | 1.0 |
| Velocity | 0.9 |
| Geo Anomaly | 0.7 |
| Bot/Emulator | 1.0 |

Friendly fraud score is computed separately and combined as:

- `criminal_score = min(1.0, max(weighted criminal signals))`
- `friendly_score = max(friendly_fraud, subscription_abuse)`
- `risk_score = max(criminal_score, friendly_score)` with confidence dampening for low-confidence cases

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

Available at `/metrics` (token required if set).

Emitted in the current MVP:
- `fraud_requests_total` - Request counts by endpoint
- `fraud_decisions_total` - Decision counts by outcome
- `fraud_e2e_latency_ms` - End-to-end decision latency histogram
- `fraud_feature_latency_ms` - Feature computation latency histogram
- `fraud_scoring_latency_ms` - Scoring latency histogram
- `fraud_model_latency_ms` - ML inference latency histogram (when ML enabled)
- `fraud_policy_latency_ms` - Policy evaluation latency histogram
- `fraud_slow_requests_total` - SLA breach counter
- `fraud_errors_total` - Error counts by type
- `fraud_cache_hits_total` - Idempotency cache hits
- `fraud_postgres_latency_ms` - Postgres operation latency (evidence + idempotency)
- `fraud_model_version_info` - Model version by variant (when ML enabled)
- `fraud_model_decisions_total` - ML decisions by variant + outcome
- `fraud_model_fallback_total` - ML fallback counts (rules-only)
- `fraud_model_approval_rate` - Approval rate by model variant
- `fraud_model_fraud_rate` - Fraud rate by model variant (lagged by chargebacks)
- `fraud_model_fallback_rate` - Fallback rate by model variant

Defined but not yet populated in this codebase:
- `fraud_cache_misses_total`
- `fraud_approval_rate`
- `fraud_block_rate`
- `fraud_risk_score`
- `fraud_criminal_score`
- `fraud_friendly_score`
- `fraud_detector_triggers_total`
- `fraud_redis_latency_ms`
- `fraud_component_health`
- `fraud_policy_version`

### Dashboard

The primary observability UI is the Streamlit dashboard (`dashboard.py`), which provides decision distribution, latency charts, decision history, policy inspection, and threshold management. A Grafana dashboard is not included in this repo; Prometheus metrics are available at `/metrics` for integration with external monitoring tools.

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

- [x] ML model integration (gated behind ML_ENABLED; training pipeline implemented)
- [x] Champion/challenger routing (deterministic hash routing implemented)
- [x] Replay framework (implemented via `scripts/replay_analysis.py`)
- [ ] Automated retraining scheduler
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

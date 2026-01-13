# Fraud Detection Platform

Real-time payment fraud detection system with velocity-based rules, ML-ready architecture, and comprehensive observability.

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
- **Friendly Fraud Scoring** - Chargeback pattern recognition

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
python -c "from scripts.init_db import init; init()"

# Start API server
uvicorn src.api.main:app --reload --port 8000
```

### Running the Dashboard

```bash
# In a separate terminal
streamlit run dashboard.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501) for the demo dashboard.

## API Reference

### Decision Endpoint

```bash
POST /decide
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

### Other Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/policy/version` | Current policy version |
| POST | `/policy/reload` | Hot-reload policy config |
| GET | `/metrics` | Prometheus metrics |

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
version: "1.0.0"
rules:
  card_testing:
    enabled: true
    threshold: 5
    window_seconds: 60

  velocity:
    enabled: true
    max_per_card_per_hour: 10
    max_per_merchant_per_minute: 100

  amount:
    enabled: true
    high_value_threshold: 1000
    micro_transaction_threshold: 1
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://...` |
| `POLICY_PATH` | Policy config path | `config/policy.yaml` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Detection Logic

### Card Testing Detection

Identifies rapid sequences of small transactions:

```
IF transactions_last_60s > 5
AND average_amount < $5
AND unique_merchants > 3
THEN signal: CARD_TESTING
```

### Velocity Rules

Configurable thresholds for transaction frequency:

```
Counters tracked:
- Per card per hour
- Per card per day
- Per merchant per minute
- Per IP per hour
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

Available at `/metrics`:

- `fraud_decisions_total` - Decision counts by outcome
- `fraud_latency_seconds` - Decision latency histogram
- `fraud_signals_total` - Signal trigger counts
- `fraud_policy_version` - Current policy version

### Grafana Dashboard

Import `config/grafana-dashboard.json` for pre-built visualizations.

## Documentation

- **Architecture**: [zeroleaf.dev/docs/fraud-platform/architecture](https://zeroleaf.dev/docs/fraud-platform/architecture)
- **API Reference**: [zeroleaf.dev/docs/fraud-platform/api-reference](https://zeroleaf.dev/docs/fraud-platform/api-reference)
- **Executive Overview**: [zeroleaf.dev/docs/fraud-platform/executive-overview](https://zeroleaf.dev/docs/fraud-platform/executive-overview)

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

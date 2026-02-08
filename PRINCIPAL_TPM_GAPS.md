# FraudDetection Principal TPM Gap Review (Mag7 Bar)

Date: 2026-02-08

Scope: Full repository, line-by-line review of code, configs, tests, PRDs, dashboards, and load-test assets (excluding generated caches and virtual envs).

## Findings (Ordered by Severity)

### Critical
- **No auth/RBAC on decisioning or policy mutation endpoints; CORS is fully open; metrics server is exposed without auth.** This is a governance blocker for any Mag7-grade, revenue-path system. (`FraudDetection/src/api/main.py:124`, `FraudDetection/src/api/main.py:182`, `FraudDetection/src/api/main.py:373`, `FraudDetection/src/metrics/prometheus.py:184`)
- **Evidence JSON is stored as stringified Python objects into JSONB columns, breaking auditability and downstream analytics.** (`FraudDetection/src/evidence/service.py:249`, `FraudDetection/src/evidence/service.py:250`, `FraudDetection/scripts/init_db.sql:44`)
- **PCI/PII governance is claimed but not enforced; evidence stores card BIN/last4, device ID, IP, and raw device fingerprint without tokenization/encryption or retention controls.** (`FraudDetection/FRAUD_DETECTION.md:39`, `FraudDetection/scripts/init_db.sql:29`, `FraudDetection/scripts/init_db.sql:30`, `FraudDetection/scripts/init_db.sql:34`, `FraudDetection/src/evidence/service.py:239`, `FraudDetection/src/evidence/service.py:255`)
- **Master design claims Kafka/Flink/Feast/OPA/Seldon and “Design Complete,” but implementation is a thin FastAPI+Redis+Postgres MVP.** The scope mismatch undermines “Principal TPM capstone” credibility. (`FraudDetection/FRAUD_DETECTION.md:7`, `FraudDetection/FRAUD_DETECTION.md:52`, `FraudDetection/docker-compose.yml:7`)
- **Exactly-once semantics are stated but not guaranteed.** Idempotency relies solely on Redis and fails open; evidence capture failures are silently swallowed. (`FraudDetection/FRAUD_DETECTION.md:45`, `FraudDetection/src/api/main.py:304`, `FraudDetection/src/api/main.py:329`, `FraudDetection/src/evidence/service.py:267`)

### High
- **“Safe mode / kill switch” is documented but not implemented.** Errors bubble as 500s without graceful degradation. (`FraudDetection/docs/02-Principal-TPM-Execution-Strategy.md:156`, `FraudDetection/docs/02-Principal-TPM-Execution-Strategy.md:171`, `FraudDetection/src/api/main.py:299`)
- **Feature/profile updates and evidence capture are awaited despite comments saying “async, don’t block,” adding latency to the critical path.** (`FraudDetection/src/api/main.py:271`, `FraudDetection/src/api/main.py:278`)
- **Service/merchant model mismatch:** DB schema is merchant-centric; telco implementation maps service fields into merchant columns. This will break semantics and downstream reporting. (`FraudDetection/scripts/init_db.sql:25`, `FraudDetection/src/evidence/service.py:235`)
- **Evidence schema and pipeline still refer to “merchant” even though product is telco/MSP.** This is a data model drift risk for any real deployment. (`FraudDetection/scripts/init_db.sql:25`, `FraudDetection/src/evidence/service.py:235`)
- **Hard-coded “impossible travel” is documented but not implemented.** (`FraudDetection/src/detection/geo.py:142`)

### Medium
- **ML claims vs. reality:** Roadmap says ML-ready and load testing to 1000+ RPS, but only rule-based scoring exists and the only published result is 260 RPS at 50 users. (`FraudDetection/docs/03-AI-ML-Roadmap.md:9`, `FraudDetection/docs/03-AI-ML-Roadmap.md:27`, `FraudDetection/loadtest/results/baseline_50users.md:17`)
- **Placeholder scopes not implemented:** Service profiles and subscription abuse scoring are explicitly placeholders. (`FraudDetection/src/features/store.py:249`, `FraudDetection/src/scoring/friendly_fraud.py:221`)
- **Monitoring documentation mismatch:** README says metrics are at `/metrics`, but metrics are served on a separate port with no FastAPI endpoint. (`FraudDetection/README.md:295`, `FraudDetection/src/metrics/prometheus.py:184`)
- **README references a non-existent DB init script.** (`FraudDetection/README.md:73`, `FraudDetection/scripts/init_db.sql:1`)
- **CI gate weakness:** mypy errors are ignored; coverage threshold not enforced. (`FraudDetection/.github/workflows/test.yml:66`, `FraudDetection/.github/workflows/test.yml:68`)
- **Demo dashboards use mock data rather than live telemetry.** (`FraudDetection/ui/dashboard_enhanced.py:1230`)

### Low
- **Local env file appears committed despite `.gitignore` excluding it.** This is an avoidable security hygiene issue. (`FraudDetection/.gitignore:4`, `FraudDetection/.env:1`)
- **Prometheus scrape config uses host.docker.internal, which breaks on Linux hosts.** (`FraudDetection/config/prometheus.yml:25`)
- **No container image definition for the API (only infra compose).** This limits deployment credibility. (`FraudDetection/docker-compose.yml:1`)

## Missing Principal TPM Artifacts (Not Implemented)
- Formal incident response playbook and on-call runbook (only strategy doc exists).
- Security/compliance implementation to match stated PCI/PII governance.
- Explicit SLOs with monitored alerting rules (Prometheus config has no alerts).
- Disaster recovery and data retention policy implementation.
- A/B or shadow deployment tooling beyond narrative docs.

## Documented Scope Decision (Requested)
- The capstone should explicitly state this is a **simplified compliance posture** for demo purposes: no PAN storage; sensitive identifiers are **pseudonymized via local HMAC hashing** (device_id, IP, fingerprint), retention is enforced by a scheduled purge, and storage relies on managed at‑rest encryption. This is intentionally low‑latency and low‑ops, and **not a claim of PCI DSS certification**.

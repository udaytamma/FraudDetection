# Architecture Decision Records

Key design decisions with rationale, alternatives considered, and accepted risks.

## 1) Auth/RBAC, CORS, Metrics Exposure
- From → To: Open CORS + no auth on `/decide` and policy mutation + standalone metrics port → token-gated API (`API_TOKEN`, `ADMIN_TOKEN`, `METRICS_TOKEN`), CORS allowlist from settings, `/metrics` served via FastAPI, external metrics server disabled by default.
- Why needed: Protects decisioning and policy control plane; avoids accidental exposure of metrics and governance data.
- Why chosen over other options: Token headers are the simplest low-ops gate; avoids OAuth/OIDC or service mesh complexity for a capstone.
- Risk accepted: Shared tokens lack per-user audit trails; security depends on secret management outside the app.
- Docs needed: `FraudDetection/README.md`, `FraudDetection/.env.example`, `FraudDetection/FRAUD_DETECTION.md`.

## 2) Evidence JSON Stored as Strings
- From → To: `str()` of Python objects into JSONB → `json.dumps()` with `::jsonb` casts.
- Why needed: Enables JSONB indexing, auditability, and downstream analytics.
- Why chosen over other options: Minimal change without introducing ORM models for evidence.
- Risk accepted: SQL text still relies on manual schema alignment; no schema validation at DB boundary.
- Docs needed: none (implementation change).

## 3) PCI/PII Governance and Evidence Vault
- From → To: Raw device/IP/fingerprint in primary evidence table with no retention → hashed identifiers in `transaction_evidence`, encrypted raw identifiers in new `evidence_vault` table, purge script for retention.
- Why needed: Demonstrates compliant handling while preserving 2-year evidence retention.
- Why chosen over other options: App‑managed encryption (Fernet) avoids operational overhead of KMS integration for capstone scope.
- Risk accepted: Key rotation and access controls are manual; not PCI DSS certified.
- Docs needed: `FraudDetection/FRAUD_DETECTION.md`, `FraudDetection/README.md`, `FraudDetection/.env.example`.

## 4) Architecture Scope Mismatch
- From → To: Docs implied Kafka/Flink/Feast/OPA/Seldon implemented → explicit “MVP vs Target” separation in docs.
- Why needed: Prevents misleading claims and aligns with actual repo contents.
- Why chosen over other options: Clear documentation fix avoids building unused infra.
- Risk accepted: Reduces “wow” factor; increases honesty and credibility.
- Docs needed: `FraudDetection/FRAUD_DETECTION.md`, `FraudDetection/README.md`.

## 5) Exactly‑Once Semantics
- From → To: Redis-only idempotency cache → Postgres `idempotency_records` fallback + Redis cache.
- Why needed: Ensures idempotency survives Redis outages and supports replay safety.
- Why chosen over other options: Database-backed idempotency is minimal and reliable without Kafka.
- Risk accepted: Adds DB latency and storage; still not distributed exactly-once for downstream effects.
- Docs needed: `FraudDetection/FRAUD_DETECTION.md`, `FraudDetection/.env.example`.

## 6) Safe Mode / Kill Switch
- From → To: Documented only → `SAFE_MODE_ENABLED` + `SAFE_MODE_DECISION` in API.
- Why needed: Demonstrates operational resilience and explicit fallback.
- Why chosen over other options: Config toggles are simplest for capstone.
- Risk accepted: Manual toggle; no automated circuit breaker.
- Docs needed: `FraudDetection/docs/02-Principal-TPM-Execution-Strategy.md`, `FraudDetection/.env.example`.

## 7) Async Background Updates
- From → To: Profile updates and evidence capture awaited → fire‑and‑forget background tasks with error logging.
- Why needed: Reduces latency on the decision path.
- Why chosen over other options: Avoids queue/outbox infra for capstone.
- Risk accepted: Eventual consistency; background failures require log review.
- Docs needed: none.

## 8) Service vs Merchant Model Drift
- From → To: Only merchant fields in evidence schema → added `service_id`/`service_name` columns and service profiles; merchant fields kept as legacy alias.
- Why needed: Aligns schema with telco/MSP domain and downstream reporting.
- Why chosen over other options: Preserves backward compatibility while adding correct fields.
- Risk accepted: Dual fields can confuse if not documented.
- Docs needed: `FraudDetection/FRAUD_DETECTION.md`, `FraudDetection/scripts/init_db.sql`.

## 9) Impossible Travel Detection
- From → To: Placeholder only → store last geo on card profile + implemented check.
- Why needed: Closes documented detector gap.
- Why chosen over other options: Uses existing geo fields and Redis profiles without new services.
- Risk accepted: Depends on geo accuracy; may introduce false positives.
- Docs needed: none (code-level).

## 10) Subscription Abuse Placeholder
- From → To: Placeholder → minimal heuristics using existing features.
- Why needed: Removes unimplemented placeholder in scoring pipeline.
- Why chosen over other options: Keeps scope small while still functional.
- Risk accepted: Heuristics are simplistic; higher false positives possible.
- Docs needed: none.

## 11) Monitoring Documentation Mismatch
- From → To: Metrics described on separate port → `/metrics` served on API; README aligned.
- Why needed: Consistent developer experience.
- Why chosen over other options: Keeps single port for demo deploys.
- Risk accepted: Prometheus auth is token-based (not standard).
- Docs needed: `FraudDetection/README.md`.

## 12) README DB Init Command
- From → To: Non-existent init script → `psql -f scripts/init_db.sql`.
- Why needed: Removes dead instructions.
- Why chosen over other options: Matches CI behavior; lowest maintenance.
- Risk accepted: Requires psql installed locally.
- Docs needed: `FraudDetection/README.md`.

## 13) CI Gate Weakness
- From → To: `mypy` ignored + no coverage threshold → mypy enforced, `--cov-fail-under=70`.
- Why needed: Ensures CI catches regressions.
- Why chosen over other options: Low friction; 70% threshold matches current state.
- Risk accepted: Threshold is lower than ideal; some quality gaps may persist.
- Docs needed: none.

## 14) Dashboard Mock Data
- From → To: Mock-only charts → live `/metrics/summary` telemetry with fallback to mock.
- Why needed: Demonstrates real observability signals.
- Why chosen over other options: In-memory buffer avoids extra infra.
- Risk accepted: Telemetry resets on restart; limited history.
- Docs needed: none (optional note in README).

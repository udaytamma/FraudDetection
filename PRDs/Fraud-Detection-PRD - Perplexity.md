# Product Requirements Document (PRD)
## Fraud Detection & Prevention Platform for Telecom & MSP

**Version:** 1.0  
**Date:** December 2025  
**Author:** [Your Name]  
**Project Type:** Capstone / Portfolio Project  
**Target Audience:** Hiring managers, product/technical leaders at telcos, MSPs, and tech companies  

---

## Executive Summary

This PRD outlines the development of a **fraud analytics and detection prototype** for the Telecom and Managed Service Provider (MSP) domains. The prototype is a **portfolio project** designed to demonstrate end-to-end product and technical execution, combining problem framing, solution design, clean engineering, observability, and governance thinking—all critical capabilities for product management and technical leadership roles.

**Phase 1** (8–10 weeks) will deliver a working system detecting two priority fraud types: **MSP contract/invoice anomalies** and **identity/account-based fraud**, with a clear architectural foundation for scaling to Phase 2 (call-based fraud) and Phase 3 (cross-industry collaboration).

---

## 1. Project Overview

### 1.1 What We Are Building

An **end-to-end fraud detection and analytics system** that:

- **Ingests diverse data streams** mimicking real operational contexts: MSP invoice/contract records, subscriber account activity, identity/credential events, and billing anomalies.
- **Detects fraud patterns and anomalies** using rule-based and simple ML approaches, producing risk scores with clear explanations for human analysts.
- **Provides analyst workflows** with dashboards, alerts, case management, and KPI tracking to show how fraud operations teams would adopt and use this system.
- **Emphasizes operational realism**: batch/micro-batch processing (near real-time ready for Phase 1; true inline blocking deferred to Phase 2), practical governance, compliance awareness, and clear documentation of limitations.

### 1.2 Why This Project Matters

**For Hiring Managers & Technical Leaders:**  
This project demonstrates:
- **Problem-space expertise**: Understanding of telecom/MSP fraud types, business impact, regulatory context, and cross-stakeholder dynamics (telcos, banks, regulators).
- **Product thinking**: Clear personas, use cases, success metrics, documented constraints, and awareness of trade-offs (false positives vs. operational burden).
- **Technical execution**: Clean, typed, well-tested code; observability; secure by design; reproducible deployments; and honest documentation of edge cases and scope limitations.
- **Portfolio-grade delivery**: A public GitHub repo, working prototype on a real platform, >80% test coverage, clear architecture, and evidence of iterative refinement.

**For the Fraud/Risk Community:**  
This project provides a **reusable template and reference implementation** for fraud detection in telco/MSP contexts, showcasing best practices in:
- Synthetic data generation for fraud scenarios.
- Rule-based + analytical detection pipelines.
- Analyst-friendly UI and alerting workflows.
- Operational KPIs and process design.

### 1.3 Users & Personas (Real-World Framing)

**Primary Users (Operational):**
1. **Fraud Analyst (Telco/MSP)** – Reviews alerts, investigates cases, provides disposition; uses risk scores and related-entity views to triage and decide on action.
2. **Operations/Network Engineer** – Monitors CDR data, billing anomalies, and contract fulfillment; needs anomaly detection to catch operational or fraudulent issues early.
3. **Fraud Manager/Risk Officer** – Sets policies, tunes thresholds, reviews KPIs, and ensures compliance with regulatory expectations.

**Secondary Users (Strategic):**
- **Compliance / InfoSec Officer** – Understands how fraud detection interacts with data privacy, identity management, and joint liability frameworks (e.g., GDPR, PSD3).
- **Business/Revenue Teams** – Needs visibility into fraud losses, false positive costs, and conversion impact of friction added by fraud controls.

**Your Actual Audience (Why You're Building This):**
- Hiring managers, product leads, and senior engineers at Google, Apple, high-growth fintech/telco startups evaluating your **product sense, technical depth, and execution discipline**.

---

## 2. Business Context & Problem Statement

### 2.1 Industry Landscape

Telecom and MSP fraud is a **multi-billion-dollar problem** globally. Fraud takes many forms:

**Telecom Fraud Types** (per LexisNexis and industry sources):
- **Subscription Fraud**: Criminals use stolen identities to apply for services; telcos bear loss.
- **First-Party Fraud**: Genuine account holder intentionally defaults or files chargebacks.
- **Synthetic Identity Fraud**: Combination of real + fabricated data to open fake accounts.
- **Account Takeover (ATO)**: Fraudsters gain control of genuine accounts via compromised credentials, change details, make unauthorized transactions.
- **Credential Testing**: Attackers test stolen credentials against accounts (often from dark web data breaches) to confirm access.
- **Bot Attacks**: Automated attacks on login/signup; bot attacks at login rose **597% globally** (2022, LexisNexis data).

**MSP-Specific Fraud**:
- **Invoice/Contract Anomalies**: Duplicate invoices, overlapping service periods, inflated labor rates, ghost projects, or time-entry fraud.
- **Labor Time Fraud**: Overbilling for services not rendered or falsifying billable hours.
- **Subscription Abuse**: Free trial abuse, rapid account cycling, unauthorized resale of access.

### 2.2 Current State & Gaps

Today, most telcos and MSPs:
- Rely on **manual review** and legacy rule engines (often inflexible, hard to update).
- Lack **real-time behavioral context** and cross-source correlation.
- Struggle to **balance fraud prevention** with customer experience (high false positives → operational burden and customer churn).
- Have **unclear responsibility chains** when fraud crosses organizational boundaries (e.g., a telco and a bank both impacted by APP scams).
- Face **growing regulatory pressure** to demonstrate proactive fraud detection and coordinated industry response.

### 2.3 Our Approach: Phase-Based Evolution

**Phase 1 (Capstone MVP):** Build a polished, documented prototype that proves:
- Ability to model fraud scenarios in synthetic data.
- Effective rule + analytics-based detection for 2 priority fraud types.
- Operational workflows (alert triage, case management, KPI tracking).
- High engineering standards (test coverage, observability, clear documentation).

**Phase 2 (Roadmap):** Add ML depth, more fraud types, richer UX, and deeper analytics.

**Phase 3 (Vision):** Enable cross-industry fraud intelligence sharing (inspired by GSMA "Scam Signal" and PwC joint-responsibility frameworks).

---

## 3. Core Requirements (Prioritized)

### 3.1 Must-Have (Phase 1 MVP)

#### 3.1.1 Synthetic Data & Scenarios

- [ ] **MSP Contract/Invoice Dataset**
  - Schema: Contract ID, MSP ID, Service Type, Quantity, Unit Cost, Invoice Date, Paid Date, Time Entry Records, Labor Hours, Billing Rate.
  - Normal behavior: Consistent billing, realistic invoice cycles, aligned time entries.
  - Fraud scenarios:
    - **Duplicate invoices**: Same contract, same dates, multiple invoice records.
    - **Overlapping periods**: Time entries covering same hours by multiple contractors.
    - **Rate anomalies**: Sudden spikes in hourly rates or bulk discounts.
    - **Ghost projects**: Invoices with no corresponding time entries or contracts.
  - **Target scale**: 50k–100k invoice records, 5–10% flagged as anomalous.

- [ ] **Identity/Account-Based Dataset**
  - Schema: Subscriber ID, Account Creation Date, Device ID, IP Address, Email, Phone Number, Login Events, Credential Change Events, Payment Methods, Account Status.
  - Normal behavior: Stable login patterns, periodic credential updates, consistent device/IP.
  - Fraud scenarios:
    - **Credential testing**: Multiple failed logins from different IPs followed by success.
    - **Account takeover (ATO)**: Abrupt device/IP changes, rapid credential resets, suspicious payment method additions.
    - **Synthetic identity**: New account with rare device/email combinations, unusual behavioral patterns.
    - **SIM swap indicators** (Phase 2): Phone number changes without corresponding device/account reconciliation.
  - **Target scale**: 100k–200k subscriber records with 5–8% flagged anomalies.

- [ ] **Synthetic Data Generation** (Python / Pandas)
  - Realistic distributions: Call durations, invoice amounts, login frequency (daily, weekly patterns).
  - Fraud-scenario generators: Separate logic for creating each fraud type to avoid overfitting detection to generation.
  - **Noise injection**: Random variations (missing fields, delays, data quality issues) to prevent toy-like perfection.
  - **Labeled data**: Clear ground truth for testing and measuring detection accuracy.

#### 3.1.2 Detection Engine

- [ ] **Rule-Based Anomaly Detection**
  - **MSP Fraud Rules**:
    - Duplicate invoice detection (same contract ID, service type, amount within 7 days).
    - Overlapping time-entry detection (same contractor, overlapping hours on same date).
    - Rate anomaly detection (deviation >2σ from historical contractor rates).
    - Ghost project detection (invoices with no linked time entries).
  - **Identity Fraud Rules**:
    - Credential testing pattern (N failed logins + 1 success in <1 hour).
    - Device/IP change detection (new device/IP accessing account after stable period).
    - Rapid credential change (multiple password resets in <24 hours).
    - Payment method churn (>3 payment method changes in <7 days).

- [ ] **Analytical Anomaly Detection**
  - **Z-score / percentile-based outlier detection** on numeric features (invoice amount, contractor rate, login frequency).
  - **Rolling window aggregation**: Detect unusual velocity (e.g., 10x normal invoice volume in a week).
  - **Entity-level features**: Account age, historical fraud indicators, related entity risk (e.g., if a contractor is flagged, related contracts at higher risk).

- [ ] **Risk Scoring & Explanation**
  - Composite risk score per entity (0–100 scale):
    - **MSP**: Per invoice, per contractor, per MSP organization.
    - **Identity**: Per account, per device, per IP/email.
  - **Explainability**: List contributing factors with weights (e.g., "Rate anomaly [40%], New contractor [20%], Duplicate invoice history [20%]").
  - **Severity tiers**: Green (<30), Yellow (30–70), Red (>70) with actionable guidance per tier.

#### 3.1.3 API & Backend Services

- [ ] **Data Ingestion API**
  - `POST /api/v1/ingest/contracts` – Batch upload MSP contract/invoice records.
  - `POST /api/v1/ingest/accounts` – Batch upload subscriber account and login events.
  - **Idempotent processing**: Re-submitting the same batch doesn't create duplicate alerts.
  - **Validation & error handling**: Clear error messages for malformed records; graceful degradation.

- [ ] **Alert API**
  - `GET /api/v1/alerts` – List alerts with filters (date range, fraud type, risk score range, status).
  - `GET /api/v1/alerts/{alert_id}` – Detail view with context (entity history, related entities, rule triggers).
  - `PATCH /api/v1/alerts/{alert_id}` – Update status (New → Under Review → Closed) and add disposition (TP/FP/Benign) + notes.

- [ ] **Risk Score API**
  - `GET /api/v1/risk-score/{entity_type}/{entity_id}` – Return risk score, contributing factors, and context.
  - **Response time**: p95 <300 ms.

#### 3.1.4 Analyst Dashboard (Web UI)

- [ ] **Alert List View**
  - Table of recent alerts: timestamp, fraud type, entity (contractor/account), risk score, status, assigned analyst.
  - Filters: date range, fraud type, risk tier, status.
  - Quick actions: Mark as reviewed, change disposition, add tags.

- [ ] **Alert Detail View**
  - Risk score breakdown with contributing factors and explanations.
  - Entity profile (contractor/account history, related entities).
  - Related alerts (other flags on same entity or similar patterns).
  - Timeline view: Key events (invoice dates, login attempts, credential changes) in context.
  - Analyst workflow: buttons to disposition (TP/FP/Benign) with comment field.

- [ ] **Trend Dashboard**
  - Charts: alerts per day by fraud type, distribution by risk tier, analyst throughput (cases resolved per hour).
  - High-level KPIs: total fraud value detected, false positive rate, mean time to review.

#### 3.1.5 Alerting & Workflow (MVP)

- [ ] **Alert Queue / Case Management**
  - Simple database table: alert ID, entity details, risk score, status, disposition, analyst assigned, created/updated timestamps.
  - **Workflow**: Analyst sees alert → reviews context → marks disposition + notes → closes.
  - No complex SLA logic in Phase 1; simple KPI tracking (time from alert to disposition).

- [ ] **Notification Stub**
  - Optional webhook or email integration stub for high-risk alerts (>80 score).
  - Not fully implemented; placeholder showing how notifications would integrate in Phase 2.

#### 3.1.6 Engineering Excellence

- [ ] **Test Coverage**
  - >80% coverage for backend logic: data models, rule engine, scoring, API endpoints.
  - Unit tests for detection rules, synthetic data generators, risk scoring functions.
  - Integration tests for end-to-end data flows (ingest → detect → alert).
  - Mocked DB/API calls to keep tests fast and isolated.

- [ ] **Code Quality**
  - **Type hints** on all public functions and modules (Python dataclasses, Pydantic models).
  - **Docstrings** for service-level and core logic modules (Google or NumPy style).
  - **Linting**: isort, black, flake8 enforced via pre-commit hooks.
  - **No TODOs or placeholders**; all features in Phase 1 scope are complete.

- [ ] **Edge Case Documentation**
  - Clear section in codebase README listing handled vs. unhandled edge cases:
    - **Handled**: Missing fields (use sensible defaults), duplicate records (idempotent processing), clock skew (<5 min), database connection retries.
    - **Unhandled**: Real-time network telemetry (Phase 2), geographic/regulatory routing, complex ML models.
    - **Out of scope for Phase 1**: Encrypted data, high-volume streaming, sub-second latency, cross-organization data sharing.

- [ ] **GitHub Repository**
  - Public repo with clear structure: `/backend` (FastAPI services), `/frontend` (React UI), `/data` (synthetic generators), `/docs` (architecture, decisions).
  - **CI/CD pipeline**: GitHub Actions running tests, linting, coverage checks on every push; status badge in README.
  - **Architecture Decision Records (ADRs)**: Short docs explaining why we chose certain approaches (e.g., rule-based over pure ML for Phase 1).
  - **README**: Covers problem, solution overview, quick start, deployment, testing, and contribution guidelines.

#### 3.1.7 Deployment & Observability

- [ ] **Containerization**
  - Docker images for backend (FastAPI + dependencies) and frontend (Node build).
  - `docker-compose.yml` for local development (backend, postgres, frontend).
  - Single-step deployment to public cloud (Railway.io as your stated preference; Render/Fly.io as fallbacks).

- [ ] **Basic Observability**
  - **Structured logging**: JSON logs with request ID, timestamp, severity, service, message.
  - **Metrics**: Request count, latency (p50/p95/p99), error rate; exposed via `/metrics` endpoint (Prometheus format).
  - **Health checks**: `/health` endpoint returning service status, database connectivity.
  - **Observability dashboard**: Simple Grafana/Datadog panel (or cloud platform's native dashboard) showing alerts/minute, error rate, p95 latency.

- [ ] **Secrets & Configuration**
  - Environment variables for sensitive data (DB credentials, API keys); `.env.example` in repo showing all required vars.
  - No hardcoded secrets; clear documentation on how to set them in production.

---

### 3.2 Should-Have (Phase 2)

- [ ] **Enhanced ML/Analytics**
  - Unsupervised anomaly detection model (e.g., Isolation Forest, Local Outlier Factor) running alongside rules.
  - Feature store for reusable fraud features (login frequency, payment method churn, invoice variance).
  - Model performance tracking: precision, recall, F1-score on held-out synthetic test sets.

- [ ] **Multi-Channel Coverage**
  - Extend to call/SMS event data (simulated CDR-like records) to complement account-based detection.
  - SIM-swap indicators and device-binding anomalies.
  - Cross-channel identity risk: same person flagged on multiple channels.

- [ ] **Richer UX & Configuration**
  - Configurable rules via UI or configuration files (no code redeploy needed to tune thresholds).
  - Filtered timelines and investigation views showing related entities and campaign patterns.
  - Bulk actions: mark multiple alerts, assign to team members.

### 3.3 Nice-to-Have (Phase 3 & Future)

- [ ] **Cross-Industry Collaboration & "Fraud Signal API"**
  - Design (and stub) an external API for sharing risk scores or fraud intelligence with banks or partner systems.
  - Inspired by GSMA "Scam Signal" and SG/AU regulatory frameworks.
  - Illustrative compliance and liability diagrams: who is responsible for what in a joint fraud case.

- [ ] **Advanced Analytics & Modeling**
  - Graph-based fraud ring detection (connecting related fraudsters across accounts/contractors).
  - Time-series forecasting for fraud trends and seasonal patterns.
  - Explainable AI techniques (SHAP, LIME) for model interpretability.

---

## 4. Non-Functional Requirements

### 4.1 Performance

**Phase 1 Targets** (batch/micro-batch processing):

- **Data Processing**:
  - Ingest and detect fraud across 100k synthetic records in <60 seconds on a single modest cloud instance (2 CPU, 4 GB RAM, as on Railway).
  - Rule engine latency: <1 second per batch of 1,000 records.

- **API Response Times**:
  - `GET /alerts`: p95 <500 ms for typical queries (1,000-record result set with filters).
  - `GET /risk-score/{entity}`: p95 <300 ms per entity.
  - `POST /ingest`: Acknowledge batch within <5 seconds; processing happens asynchronously.

### 4.2 Reliability & Error Handling

- **Graceful Degradation**:
  - Malformed records: Log error, skip record, continue processing.
  - Missing fields: Use sensible defaults (e.g., NULL for invoice date = assume pending).
  - Database connection issues: Retry with exponential backoff; return 503 Service Unavailable to client if threshold exceeded.
  - Duplicate events: Idempotent processing (duplicate batch re-submission doesn't create duplicate alerts).

- **Data Consistency**:
  - All writes to alerts/cases transactional (ACID guarantees via PostgreSQL).
  - No orphaned alerts (if entity is deleted, alert is marked as archived, not deleted).

### 4.3 Code Quality

- **Type Hints**: Required on all public functions and module-level variables (Python 3.10+).
- **Docstrings**: Google or NumPy style for all service-level and core logic modules.
- **Test Coverage**: >80% for backend; >70% overall (including UI integration tests).
- **Linting**: isort, black, flake8 configured in pre-commit; CI enforces.
- **Documentation**: README with architecture overview, setup, testing, deployment, and edge cases.

### 4.4 Security & Compliance (Prototype-Level)

- **Data**:
  - No real PII in Phase 1 (synthetic data only).
  - Document how real PII would be handled: masking, tokenization, regional storage.

- **Access Control**:
  - Simple role-based access (e.g., analyst, manager, admin) in Phase 1 MVP.
  - API authentication via simple token or API key (Bearer token in Authorization header).
  - Passwords hashed with bcrypt; session tokens short-lived.

- **Compliance Narrative**:
  - Document GDPR/PSD3 expectations: data minimization, retention policy, consent, cross-border sharing.
  - Highlight joint responsibility: telco detects ATO; bank detects APP scam; both must coordinate.
  - Governance: clear audit trails (who changed an alert status and when).

### 4.5 Observability & Monitoring

- **Logging**:
  - Structured JSON logs with context (request ID, timestamp, severity, service name, message).
  - Log levels: DEBUG (development), INFO (key events), WARNING (recoverable issues), ERROR (failures).

- **Metrics** (Prometheus format):
  - Request throughput (requests/sec by endpoint).
  - Latency (p50, p95, p99 by endpoint).
  - Error rate (5xx, 4xx by endpoint).
  - Business metrics: alerts created per hour, dispositions per hour.

- **Health & Alerting**:
  - `/health` endpoint for liveness/readiness checks (container orchestration).
  - Alert if error rate >5% or latency p95 >1 sec; integration with platform's monitoring (Railway/Render alerts).

---

## 5. Technical Stack

### 5.1 Recommended Stack (Your Preference)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend Language** | Python 3.10+ | Strong fraud analytics ecosystem, clear code, easy to reason about. |
| **Web Framework** | FastAPI | Type hints, automatic OpenAPI docs, async support, fast. |
| **Database** | PostgreSQL 14+ | ACID guarantees, JSON support for flexible schemas, battle-tested. |
| **ORM / Query** | SQLAlchemy + Alembic | Type-safe, migrations, widely adopted. |
| **Data Processing** | Pandas / Polars | Fraud feature engineering, easy to test, familiar. |
| **Async Task Queue** | Celery + Redis (optional for Phase 1) | Optional: if batch processing takes >5 sec, background jobs; keep simple in Phase 1. |
| **Frontend Framework** | React 18+ | Component-based, state management, wide hiring pool familiarity. |
| **UI Library** | Material-UI or shadcn/ui | Professional, accessible, documentation. |
| **Frontend Build** | Vite | Fast dev server, optimized builds. |
| **Containerization** | Docker + Docker Compose | Single-step local dev; standard deployment. |
| **Cloud Platform** | Railway.io (preferred); Render/Fly.io fallback | Your stated preference; Railway supports Python, PostgreSQL, easy deploys. |
| **Testing** | pytest (backend) + Vitest/Jest (frontend) | Industry standard, great fixtures and parameterization. |
| **Linting / Formatting** | isort, black, flake8 | Python best practices; pre-commit hooks. |
| **API Documentation** | FastAPI auto-generated OpenAPI + supplementary markdown docs | Automatic from type hints; Swagger UI for manual testing. |
| **LLM (Optional) for Text Fields** | Mistral-7B or similar from Hugging Face | Local, free, for synthetic text generation or scam-transcript classification; not core detection. |

### 5.2 Rationale & Alternatives

**Why Python/FastAPI?**
- Strong data science ecosystem (Pandas, NumPy, scikit-learn for Phase 2 ML).
- Type hints and automatic API docs reduce friction for reviewers.
- Easy to explain fraud logic in plain code.

**Why PostgreSQL?**
- ACID guarantees for financial/fraud data.
- JSON columns for flexible fraud event schemas.
- Scales to millions of records without complexity.

**Why React?**
- Wide recognition; hiring managers understand it.
- Component-based, easy to test, rich ecosystem of UI libraries.
- Alternatives (Vue, Svelte, or even Streamlit for faster iteration) acceptable if you prefer.

**LLM Choice:**
- Use a small, locally-deployable model (e.g., Mistral-7B, Llama-2-7B) from Hugging Face for:
  - Generating synthetic invoice descriptions and account metadata.
  - Classifying scam transcripts (Phase 2+).
  - Explaining fraud scenarios in natural language.
- **Not** using LLM for core numeric anomaly detection (rules + classic ML sufficient and more interpretable).

---

## 6. Data Model & Synthetic Scenarios

### 6.1 MSP Fraud: Contract/Invoice Schema

**Tables/Collections:**

```
MSPs (organizations)
├── msp_id (PK)
├── msp_name
├── country
├── industry (healthcare, finance, other)
└── fraud_loss_history

Contractors
├── contractor_id (PK)
├── msp_id (FK)
├── contractor_name
├── email
├── rate_per_hour
├── hire_date
└── fraud_flag (boolean)

Contracts
├── contract_id (PK)
├── msp_id (FK)
├── client_name
├── service_type (managed_it, hr_services, compliance)
├── start_date
├── end_date
└── status (active, completed, cancelled)

Invoices
├── invoice_id (PK)
├── msp_id (FK)
├── contract_id (FK)
├── amount
├── invoice_date
├── due_date
├── paid_date
├── status (draft, sent, paid, disputed)
└── description (LLM-generated realistic text)

TimeEntries
├── entry_id (PK)
├── contractor_id (FK)
├── contract_id (FK)
├── invoice_id (FK, optional)
├── work_date
├── hours
├── description
└── billable (boolean)
```

### 6.2 Identity Fraud: Account Schema

**Tables/Collections:**

```
Subscribers
├── subscriber_id (PK)
├── email
├── phone_number
├── account_created_date
├── status (active, suspended, closed)
├── region (US, EU, APAC)
└── fraud_flag (boolean)

Accounts
├── account_id (PK)
├── subscriber_id (FK)
├── account_type (postpaid, prepaid, enterprise)
├── billing_address
├── created_date
└── status

Devices
├── device_id (PK)
├── subscriber_id (FK)
├── device_type (phone, tablet)
├── imsi / imei (simulated)
├── first_seen
└── last_seen

LoginEvents
├── event_id (PK)
├── subscriber_id (FK)
├── device_id (FK)
├── ip_address
├── timestamp
├── status (success, failed)
└── failure_reason (invalid_password, account_locked)

PaymentMethods
├── payment_id (PK)
├── subscriber_id (FK)
├── method_type (credit_card, bank_account, digital_wallet)
├── last_4_digits
├── added_date
└── primary (boolean)

CredentialChangeEvents
├── event_id (PK)
├── subscriber_id (FK)
├── change_type (password, email, phone_number)
├── timestamp
└── initiated_by (self, admin, fraud_team)
```

### 6.3 Synthetic Data Generation Strategy

**Goals:**
1. **Realistic distributions**: Call durations, invoice amounts, contractor tenure follow actual market data.
2. **Fraud scenarios well-defined and separable**: Fraud-generation rules distinct from detection rules.
3. **Imbalanced classes**: 90–95% normal, 5–10% fraudulent (matching real-world rarity).
4. **Noise & quality issues**: Simulated missing fields, duplicates, timing edge cases.

**Generation Approach:**

```python
# Phase 1: Base normal data generators
def generate_normal_msps(n=50):
    """Realistic MSP orgs with normal invoice patterns."""
    ...

def generate_normal_invoices(msps, n=50000):
    """Normal invoices: consistent timing, realistic amounts, aligned time entries."""
    ...

def generate_normal_subscribers(n=100000):
    """Normal accounts: stable logins, periodic credential updates."""
    ...

# Phase 2: Fraud scenario generators (separate logic)
def inject_duplicate_invoices(invoices, fraud_rate=0.03):
    """Create duplicates: same contract, same amount, within 7 days."""
    ...

def inject_overlapping_time_entries(time_entries, fraud_rate=0.05):
    """Create overlaps: same contractor, same date, overlapping hours."""
    ...

def inject_ato_patterns(logins, fraud_rate=0.04):
    """Create ATO indicators: device/IP change, rapid login failures."""
    ...

# Phase 3: Combine with noise
def add_quality_noise(df, missing_rate=0.02):
    """Inject realistic data quality issues."""
    ...

# Final: labeled dataset
def generate_synthetic_dataset(config):
    """
    Generate train/test datasets with clear labels.
    Returns: (X_train, y_train, X_test, y_test)
    """
    ...
```

**Dataset Sizes (Phase 1):**
- MSP Invoices: 50,000 records, 5% fraudulent (2,500 fraud cases).
- Subscriber Accounts: 100,000 records, 8% fraudulent (8,000 fraud cases).
- Total: ~150k base records; should process in <60 sec on a modest instance.

---

## 7. Development Phases & Timeline

### 7.1 Phase 1: Problem Framing & MVP (8–10 weeks, ~80–100 hours)

**Assumption:** ~10–15 focused hours/week, iterative refinement.

| Week | Tasks | Deliverables |
|------|-------|--------------|
| **1–2** | Finalize PRD, personas, fraud scenarios. Design data schemas and synthetic generators. | PRD (this doc), schema diagrams, fraud scenario specs, synthetic data blueprint. |
| **3–4** | Implement synthetic data generators (MSP + identity), persistence, basic backend services (ingest, data layer). | Synthetic datasets (training/test), `/ingest` API, database models, >60% test coverage. |
| **5–6** | Implement detection engine (rules + analytics), risk scoring, `/alerts` + `/risk-score` APIs. | Detection rules tested, risk-score function with explainability, API endpoints green. |
| **7** | Build React UI (alert list, detail, filters, disposition workflow). | Basic UI functional, manual testing complete. |
| **8** | Deploy to Railway, add observability (logging, metrics, `/health`). | Live demo accessible, basic monitoring in place. |
| **9–10** | Polish, documentation (README, architecture, ADRs, edge cases), CI setup, final testing. | Public GitHub repo, CI green, >80% backend coverage, docs complete. |

**Success Criteria (Measurable):**
- ✓ GitHub repo public with clean structure.
- ✓ >80% backend test coverage (pytest + coverage.py report).
- ✓ CI pipeline passing on every push.
- ✓ Deployed demo live on Railway; alert list and detail views functional.
- ✓ Synthetic data: 2 fraud scenarios correctly detected with <10% false-positive rate in test data.
- ✓ PRD, architecture doc, and edge-case doc all readable in <15 minutes.
- ✓ README with clear problem statement, setup instructions, testing, and deployment.

### 7.2 Phase 2: Analytics Depth & Multi-Channel Coverage (6–8 weeks)

**Topics:**
- Unsupervised ML (Isolation Forest, LOF) + rule fusion.
- Call-based fraud patterns (simulated CDR data mimicking IRSF/Wangiri).
- Richer UI (configurable rules, investigation timelines, related entities).
- Improved accuracy metrics and model performance tracking.

### 7.3 Phase 3: Collaboration & Production-Readiness Narrative (4–6 weeks)

**Topics:**
- Fraud Signal API design and stub.
- Cross-industry compliance and liability frameworks.
- Advanced observability and 24/7 operational readiness story.
- Scalability roadmap (from prototype to production).

---

## 8. Key Performance Indicators (KPIs)

### 8.1 Technical KPIs (Portfolio/Demo)

| KPI | Target (Phase 1) | Measurement |
|-----|-----------------|-------------|
| **Test Coverage** | >80% | pytest coverage report (backend logic). |
| **API Response Time (p95)** | <500 ms (alerts), <300 ms (risk-score) | Observability dashboard / Prometheus metrics. |
| **Data Processing Speed** | 100k records in <60 sec | Synthetic data ingest benchmark. |
| **Fraud Detection Accuracy** | >90% precision & recall on test data | Confusion matrix on held-out synthetic set. |
| **Code Quality (Linting)** | 0 flake8 errors, black/isort clean | CI status. |
| **Deployment Uptime** | >95% (Phase 1 demo) | Platform's status page. |

### 8.2 Operational KPIs (Real-World Framing)

| KPI | Baseline (From Synthetic Data) | Interpretation |
|-----|-------------------------------|-----------------|
| **Alerts per Day** | 50–100 (per 100k records scanned) | Volume of fraud flags generated. |
| **False Positive Rate** | <10% | % of alerts that are benign (tune threshold to manage). |
| **Mean Time to Disposition** | <1 hour (analyst workflow) | How long analysts spend per alert. |
| **Fraud Detection Rate** | >85% (on synthetic test set) | % of injected fraud cases caught. |
| **Analyst Throughput** | 10–20 cases/hour | Cases reviewed and dispositioned per analyst per hour. |

### 8.3 Business KPIs (Narrative for Job Interviews)

| KPI | Relevance |
|-----|-----------|
| **Fraud Loss Prevented** | $ or % revenue protected (in real deployment). |
| **Customer Impact** | Reduction in churn due to fraud-related account lockouts. |
| **Operational Efficiency** | Analyst hours saved via automation and clear triage. |
| **Regulatory Compliance** | Industry report submissions, audit trail completeness. |

---

## 9. Technical Constraints & Edge Cases

### 9.1 Handled in Phase 1

- ✓ **Missing fields**: Use sensible defaults (e.g., NULL invoice_date = pending state).
- ✓ **Duplicate events**: Idempotent batch ingestion (re-submit same data = no duplicate alerts).
- ✓ **Clock skew** (<5 min): Tolerance in time-window matching for related events.
- ✓ **Database connection failures**: Retry with exponential backoff; graceful error to client.
- ✓ **Malformed JSON**: Validation errors logged; record skipped, batch continues.
- ✓ **Scaling to ~1M records**: Queries indexed on key fields; batch processing keeps memory footprint low.
- ✓ **Type safety**: All type hints present; mypy-clean codebase.
- ✓ **Test isolation**: Unit tests use in-memory DB or mocks; no flaky tests.

### 9.2 Explicitly Out of Scope (Phase 1)

- ✗ **Real-time network telemetry**: No inline integration with live CDR/billing streams (Phase 2+).
- ✗ **Sub-second latency**: Batch/micro-batch processing; not suitable for on-path blocking.
- ✗ **Encrypted data at rest/in transit**: Assume secure infrastructure; no custom crypto logic.
- ✗ **Complex ML models** (deep learning, LLM-based detection): Keep to rules + classic ML (Isolation Forest) for interpretability.
- ✗ **Cross-organization data sharing**: Single-org tool in Phase 1; Phase 3 designs cross-org API.
- ✗ **Geographic/regulatory routing**: Assume single region (US/EU/APAC); no split-horizon DNS.
- ✗ **High-volume streaming**: Kafka/Pulsar integration deferred to Phase 2+.
- ✗ **Real PII**: Synthetic data only; no GDPR-compliance testing on real data.

---

## 10. Governance, Compliance & Documentation

### 10.1 Governance

**Decision-Making:**
- Product decisions (feature prioritization, fraud types to cover): PRD + Architecture Review notes in repo.
- Technical architecture (stack, patterns, libraries): Architecture Decision Records (ADRs) in `/docs/adr/`.
- Fraud rule updates: Version-controlled rule definitions; changes logged with rationale.

**Code Review & Quality Gates:**
- All PRs require review (linting + tests passing) before merge.
- Coverage must remain >80%; PRs that reduce coverage are blocked.
- CI/CD enforces code quality checks; no manual gate needed.

### 10.2 Compliance & Privacy

**Data Handling (Even for Synthetic Data):**
- Document how real PII would be handled: masking (last 4 digits only for cards), tokenization (subscriber ID instead of SSN), regional storage (EU data in EU).
- Data retention: synthetic data can be deleted at project end; transactional data (alerts) retained per organizational policy.
- Cross-border transfer: design assumes single region for Phase 1; Phase 3 adds multi-region considerations.

**Audit & Transparency:**
- Audit trail: all alert status changes logged with timestamp, user, reason.
- Explainability: every alert includes risk-score breakdown and contributing factors.
- Governance documentation: README includes section on how to interpret and tune fraud rules.

### 10.3 Documentation

| Document | Location | Audience |
|----------|----------|----------|
| **README** | `/README.md` | Everyone; quick start, problem context, setup. |
| **Architecture** | `/docs/architecture.md` | Engineers; system design, data flow, module breakdown. |
| **Data Model** | `/docs/data_model.md` | Data engineers, analysts; schema, relationships, examples. |
| **Fraud Scenarios** | `/docs/fraud_scenarios.md` | Product, fraud analysts; detailed case definitions, detection logic. |
| **API Reference** | FastAPI auto-generated OpenAPI + `/docs/api.md` | Developers; endpoint specs, request/response examples. |
| **Edge Cases** | `/docs/edge_cases.md` | QA, support; handled vs. unhandled issues, limitations. |
| **Operational Guide** | `/docs/operations.md` | Fraud analysts, ops teams; how to use the system, interpret alerts, tune thresholds. |
| **Deployment Guide** | `/docs/deployment.md` | DevOps/SRE; infrastructure setup, monitoring, scaling. |
| **ADRs** | `/docs/adr/` | Engineers; architectural decisions and rationale. |

---

## 11. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Overfitting to synthetic data** | Detection fails on real data | Separate fraud-generation rules from detection rules; add noise; hold-out test set. |
| **False positives overwhelming analysts** | Poor UX, tool abandoned | Configurable thresholds, risk tiers (Green/Yellow/Red), expected FP rate in docs. |
| **Performance bottlenecks** | Ingest/detection slow on scale | Benchmark early; index DB queries; profile Python code; defer complex ML to Phase 2. |
| **Scope creep** | Miss Phase 1 deadline | Strict feature prioritization; MVP-focused; Phase 2+ is roadmap, not Phase 1. |
| **LLM complexity / cost** | Unnecessary dependencies, GPU costs | Use small open models; LLM only for text generation (optional); core detection rule/ML-based. |
| **Deployment on Railway fails** | Can't demo live | Test Railway deployment early (week 4–5); fallback to Render/Fly.io. |
| **Hiring signal unclear** | Capstone doesn't help job search | Strong documentation, clear product narrative, portfolio-grade code quality, live demo. |

---

## 12. Success Metrics Summary

**By end of Phase 1, you will have:**

1. ✅ **Public GitHub repo** with >80% backend test coverage, CI passing, clean commit history.
2. ✅ **Working prototype** deployed and live (Railway), with functioning alert list/detail UI.
3. ✅ **Two fraud scenarios** correctly modeled and detected (MSP invoicing, identity/account takeover) with <10% FP rate.
4. ✅ **Comprehensive documentation**: PRD, architecture, fraud scenarios, edge cases, operational guide.
5. ✅ **Portfolio narrative**: "I built a fraud detection platform that demonstrates problem understanding, product design, technical depth, and operational thinking—spanning data modeling, backend APIs, frontend UI, testing, observability, and governance."
6. ✅ **Hiring-manager-friendly**: Clear problem statement, realistic solutions, no hand-waving, documented trade-offs and limitations.

---

## Additional Info

### A. Synthetic Data Generation Approach

**Why Synthetic?**
- Real fraud datasets are proprietary and hard to access.
- Synthetic data lets you control fraud scenarios and ensure comprehensive coverage.
- No privacy concerns; easier to share and iterate.

**Generation Strategy:**
1. **Normal behavior baseline**: Use realistic distributions (e.g., contractor rates follow log-normal, invoice amounts follow gamma distribution).
2. **Fraud injection**: Separate generators for each fraud type; inject into base data at known rates (e.g., 5% of invoices are duplicates).
3. **Noise addition**: Introduce missing fields, timing variations, and data quality issues to avoid toy-like perfection.
4. **Separation of concerns**: Fraud-generation logic distinct from detection logic to avoid overfitting.

**Tools & References:**
- [CEUR-WS CDR Generator Paper](https://ceur-ws.org/Vol-2915/paper12.pdf): Blueprint for realistic call/communication patterns.
- [Kaggle PaySim Dataset](https://www.kaggle.com/datasets/ealaxi/paysim1): Reference for financial fraud simulation and class imbalance handling.
- [FCA Report on Synthetic Data in Financial Services](http://www.fca.org.uk/publication/corporate/report-using-synthetic-data-in-financial-services.pdf): Governance and best practices.

### B. LLM Integration (Optional, Not Core)

**Suitable Role:**
- Generating realistic synthetic text fields (invoice descriptions, account metadata, scam-call transcripts for Phase 2).
- Explaining fraud scenarios in plain language.
- Classifying scam conversation transcripts (Phase 2+).

**Not Suitable For:**
- Core numeric anomaly detection (rules + classic ML more interpretable and performant).
- Real-time decision-making (inference latency + hallucinations problematic).

**Model Recommendations:**
1. **Mistral-7B** (Hugging Face): Small, instruction-tuned, runs on CPU/modest GPU.
2. **Llama-2-7B** (Meta): Open-source, permissive license, similar size/capability.
3. **Custom Fine-Tuned Variant** (e.g., `Bilic/Mistral-7B-LLM-Fraud-Detection` on Hugging Face): Optional; shows LLM-ops skills but not essential for Phase 1.

**Cost & Deployment:**
- All open-source models: free to download and run locally.
- License check: verify commercial-use allowance per model (most permissive for portfolio projects).
- No GPU required for Phase 1 (CPU inference acceptable for text generation, ~0.5–2 sec per text).

### C. Hosting & DevOps

**Railway (Your Preference):**
- Supports Python, PostgreSQL, easy environment variables, straightforward deploys.
- Free tier sufficient for demo (100 hours/month compute, 5 GB storage).
- Scaling: paid tiers available if demo traffic grows (unlikely in Phase 1).

**Fallback Options:**
- **Render**: Similar to Railway, Gen2 instances, automatic deploys from GitHub.
- **Fly.io**: Global edge deployment, lightweight, good for small services.

**Deployment Flow:**
1. Push to GitHub.
2. Railway auto-detects Python + auto-deploys.
3. Environment variables (DB credentials, API keys) set in Railway dashboard.
4. Custom domain (optional) via Railway or DNS.

### D. Fraud Fraud Types (Expanded Reference)

**Phase 1 Priority:**

1. **MSP Contract/Invoice Anomalies**
   - Duplicate invoices: same contract, same amount, close dates.
   - Overlapping time entries: same contractor, overlapping hours, same date.
   - Rate anomalies: contractor rates deviating from historical norms.
   - Ghost projects: invoices with no associated contracts or time entries.

2. **Identity/Account-Based Fraud**
   - **Credential testing**: Multiple failed logins followed by success (automated attack).
   - **Account takeover (ATO)**: Abrupt device/IP changes, rapid credential resets, suspicious payment methods.
   - **Synthetic identity**: New account with rare device/email combinations, unusual behavior patterns.
   - **SIM swap indicators** (Phase 2): Phone number changes without device/account reconciliation.

**Phase 2 Priority:**

3. **Call-Based Fraud** (simulated CDR data)
   - **IRSF (International Revenue Share Fraud)**: Sudden spikes to specific high-cost destinations (e.g., premium lines).
   - **Wangiri**: Short repeated calls to high-cost numbers (hang up before connection; calls incomplete but charged).
   - **PBX hacking**: Unauthorized access to business phone systems; bulk international calling.
   - **SIMbox**: Termination of international calls as domestic SMS (cheaper for fraudster, revenue loss for telco).

**Industry Context (Per LexisNexis & PwC):**
- Bot attacks at login stage rose **597%** globally (2022–2024).
- Subscription fraud affects revenue directly (telco/MSP loss).
- Account takeover enables downstream scams (e.g., APP scams leveraging stolen account data).
- Cross-channel coordination needed: telcos + banks both affected by same fraudster.

### E. Regulatory & Compliance Landscape

**Key Frameworks Relevant to Your Narrative:**

1. **GDPR (EU)**: Data minimization, consent, cross-border transfer restrictions.
2. **PSD3 (EU Payments Directive)**: Joint responsibility for APP fraud prevention; customer notification requirements.
3. **FCA Guidance (UK)**: Synthetic data use for fraud detection; governance and testing.
4. **GSMA "Scam Signal"**: Telco industry initiative to share early-warning fraud signals; cross-organization coordination.
5. **SG/AU Regulatory Expectations**: Telcos and financial institutions expected to use data analytics and coordinate on fraud prevention.

**For Phase 1 Scope:**
- Document that you understand these frameworks conceptually.
- Show how your system *could* integrate data-sharing safeguards (Phase 3).
- Highlight joint responsibility: no single org solves fraud alone.

### F. Performance & Scalability Roadmap

**Phase 1: Single-Instance Batch**
- Sequential processing: ingest batch, detect anomalies, generate alerts.
- Runs on <2 CPU, 4 GB RAM instance (Railway Gen2).
- Latency: <60 sec for 100k records.

**Phase 2: Async + Micro-Batch**
- Background job queue (Celery + Redis) for long-running detection tasks.
- Micro-batches every 5–10 minutes (near real-time readiness).
- Database indexing optimization for query performance.
- Caching (Redis) for frequently accessed risk scores.

**Phase 3: Streaming + Distributed**
- Kafka/Pulsar for high-volume event streams.
- Distributed detection (Spark, Flink) for large-scale processing.
- Multi-region deployment and cross-org data sharing.
- ML model serving (MLflow, Seldon) for Phase 2+ ML models.

### G. Testing Strategy

**Unit Tests (backend):**
- Rule engine: each rule tested in isolation.
- Scoring function: edge cases (missing fields, extreme values).
- API endpoints: happy path + error cases.
- Synthetic data generators: output distributions verified.

**Integration Tests:**
- End-to-end data flow: ingest → detect → alert → disposition.
- Database transactions: ensure consistency.
- API contract: request/response shapes validated.

**System Tests (manual for Phase 1, automated in Phase 2):**
- Deployed demo: alert list loads, detail view functional, disposition workflow works.
- Observability: metrics appear in dashboard, logs structured.
- Performance: ingest 100k records, confirm <60 sec.

**Test Data:**
- Synthetic test set (hold-out): ~10% of generated data; fraud injected at known rate.
- Confusion matrix: true positives, false positives, true negatives, false negatives.
- Metrics: precision, recall, F1-score per fraud type.

### H. Portfolio Positioning

**Elevator Pitch for Hiring Managers:**

> "I built a fraud detection and analytics platform for telecom and MSP contexts—a capstone project showcasing product thinking, technical execution, and operational awareness. The system detects two fraud types (MSP invoice anomalies and account-based fraud) using rule-based and analytical approaches, presents findings to analysts via a dashboard, and tracks key metrics. It's deployed to production (Railway), has >80% test coverage, clear documentation, and is on GitHub. The project demonstrates my ability to frame complex problems, design realistic solutions, and ship polished, observable systems—skills I'm excited to bring to a product or technical-leadership role."

**Portfolio Artifacts:**
1. **GitHub repo**: Clean structure, good commit messages, clear README.
2. **Live demo**: URL to Railway deployment; working alert list and detail views.
3. **Documentation**: PRD (this doc), architecture, fraud scenarios, API reference.
4. **Code**: Type-safe, well-tested, properly formatted, no TODOs.
5. **Observability**: Live metrics dashboard showing uptime, latency, error rate.

---

## Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Dec 2025 | [Your Name] | Initial PRD; Phase 1 scope; incorporation of LexisNexis, PwC, and feasibility research. |

---

**Next Steps:**
1. Review this PRD with stakeholders (hiring manager, mentors, or peer reviewers).
2. Create GitHub repo and initialize project structure.
3. Begin Phase 1 Week 1–2: finalize fraud scenarios and synthetic data blueprint (refer to Section 6).
4. Prepare hardware/environment check: Python 3.10+, PostgreSQL 14+, GPU optional (CPU sufficient for Phase 1).
5. Set up Railway account and test deployment pipeline (Week 4–5).

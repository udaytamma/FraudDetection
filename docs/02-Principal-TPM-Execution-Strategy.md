# How I Would Drive This as a Principal TPM

**Author:** Uday Tamma | **Document Version:** 1.0 | **Date:** January 2026

---

## Overview

This document outlines the cross-functional execution strategy for the Telco Payment Fraud Detection Platform from a Principal TPM perspective. It covers stakeholder management, decision frameworks, execution sequencing, and risk mitigation approaches.

---

## Cross-Functional Partners and Engagements

### Stakeholder Map

| Partner | Role | Key Concerns | Engagement Cadence |
|---------|------|--------------|-------------------|
| **Payment Service Provider (PSP)** | Integration point | Latency SLA, error rates | Weekly sync, shared dashboard |
| **Security & Compliance** | PCI audit, PII governance | Data handling, audit trails | Bi-weekly review, sign-off gates |
| **Data Science / ML** | Model development | Feature availability, labels | Daily standup, model review weekly |
| **SRE / Platform** | Infrastructure, reliability | Capacity, failover, alerts | Sprint planning, on-call handoff |
| **Finance** | Fraud loss budget | ROI tracking, threshold economics | Monthly review, budget alerts |
| **Product** | Roadmap, customer experience | Approval rate, UX friction | Sprint demos, metric reviews |
| **Fraud Operations** | Manual review, investigations | Queue volume, tool usability | Weekly office hours, feedback loops |
| **Legal / Disputes** | Representment, compliance | Evidence quality, win rates | Quarterly review, process updates |

### RACI Matrix (Key Decisions)

| Decision | Responsible | Accountable | Consulted | Informed |
|----------|-------------|-------------|-----------|----------|
| Threshold changes | Fraud Ops | Product | DS/ML, Finance | Eng, Security |
| Model deployment | DS/ML | Eng Lead | Fraud Ops, Security | Product, Finance |
| Policy rule additions | Fraud Ops | Product | Eng, DS/ML | Finance, Legal |
| Infrastructure scaling | SRE | Eng Lead | Finance | Product |
| Evidence schema changes | Eng | Legal | Fraud Ops, Security | Finance |
| Blocklist additions | Fraud Ops | Fraud Ops | Security | Product, Eng |

---

## Decision Frameworks

### Trade-off 1: Risk vs. Approval Rate

**The Core Tension:** Every percentage point of fraud blocked potentially blocks legitimate customers.

**Framework: Expected Value Analysis**

```
For each transaction:
  Expected_Loss = P(fraud) × (amount + chargeback_fee + penalty)
  Expected_Gain = P(legitimate) × (revenue + customer_LTV_fraction)

  If Expected_Loss > Expected_Gain × risk_tolerance:
    → Apply friction or block
  Else:
    → Allow
```

**Operationalized as:**

| Scenario | Risk Score | Amount | Customer Profile | Decision |
|----------|------------|--------|------------------|----------|
| Low risk, low value | <30% | <$50 | Any | ALLOW |
| Medium risk, new customer | 40-60% | Any | <30 days | FRICTION (3DS) |
| Medium risk, established | 40-60% | Any | >90 days | ALLOW |
| High risk, any | >80% | Any | Any | BLOCK |
| High value, new card | Any | >$500 | New card | FRICTION |

**Governance:**
- Finance owns the risk tolerance parameter
- Product owns the customer experience thresholds
- Fraud Ops can adjust within guard rails without engineering
- Changes require replay testing before production

### Trade-off 2: Detection Speed vs. Accuracy

**The Core Tension:** More sophisticated detection takes more time, but payments can't wait.

**Framework: Latency Budget Allocation**

| Component | Budget | Actual | Trade-off |
|-----------|--------|--------|-----------|
| Feature lookup (Redis) | 50ms | 50ms | More features = more latency |
| Detection engine | 30ms | 20ms | More detectors = more latency |
| ML inference | 25ms | N/A | Phase 2 - adds ~20ms |
| Policy evaluation | 15ms | 10ms | More rules = more latency |
| Evidence capture | 30ms | 20ms | Async, non-blocking |
| Buffer | 50ms | 106ms | SLA headroom |
| **Total** | **200ms** | **106ms** | **47% headroom** |

**Decision Rule:**
- Any component change must model latency impact
- New features require latency benchmarking before merge
- P99 > 150ms triggers architecture review

### Trade-off 3: Manual Review vs. Automation

**The Core Tension:** Manual review is more accurate but doesn't scale and adds friction.

**Framework: Confidence-Based Routing**

```
High Confidence (>90%):
  → Automate decision (ALLOW or BLOCK)
  → No manual review
  → Post-hoc sampling for quality

Medium Confidence (60-90%):
  → Automate with audit trail
  → Sample 5% for manual review
  → Feedback loop to improve model

Low Confidence (<60%):
  → Queue for manual review
  → SLA: 4 hours for >$500, 24 hours for <$500
  → Capture analyst decision as training data
```

**Target Distribution:**
| Confidence Band | Current | Target | Manual Review |
|-----------------|---------|--------|---------------|
| High (>90%) | 60% | 75% | 0% |
| Medium (60-90%) | 25% | 22% | 5% sample |
| Low (<60%) | 15% | 3% | 100% |

---

## Execution Sequencing and De-risking

### Rollout Strategy

```
Week 1-2: Shadow Mode
├── Deploy to production infrastructure
├── Process 100% of traffic in parallel
├── Log decisions but don't act on them
├── Compare to existing system decisions
└── Validate: Latency, accuracy, stability

Week 3: Limited Production (5%)
├── Route 5% of traffic to new system
├── Remainder continues to legacy
├── Monitor: Approval rate, fraud rate, complaints
├── Kill switch: Route back to legacy if issues
└── Validate: No regression on key metrics

Week 4-5: Gradual Ramp (25% → 50% → 100%)
├── Increase traffic weekly
├── Hold each level for 48+ hours
├── Document any anomalies
├── Business sign-off at each gate
└── Full cutover only after 50% stable for 1 week
```

### Safety Rails

| Rail | Implementation | Trigger | Response |
|------|----------------|---------|----------|
| **Latency breaker** | P99 monitoring | P99 > 180ms for 5min | Alert, then safe mode |
| **Error rate breaker** | Error counter | >1% errors for 2min | Auto-rollback to legacy |
| **Approval rate guard** | Rolling metric | Drops >5% vs baseline | Alert Fraud Ops, pause ramp |
| **Block rate guard** | Rolling metric | Rises >3% vs baseline | Alert Fraud Ops, investigate |
| **Safe mode** | Fallback logic | Any critical failure | Configurable decision via `SAFE_MODE_DECISION` |

### Safe Mode Behavior

When safe mode activates:
1. Decisioning is bypassed
2. Response is deterministic based on `SAFE_MODE_DECISION` (ALLOW/BLOCK/REVIEW)
3. On-call is alerted
4. Recovery is manual for capstone (toggle off `SAFE_MODE_ENABLED`)

---

## Stakeholder Communication Plan

### Regular Cadence

| Forum | Frequency | Attendees | Agenda |
|-------|-----------|-----------|--------|
| Daily Standup | Daily | Eng, DS/ML | Blockers, progress |
| Sprint Demo | Bi-weekly | All stakeholders | Completed work, metrics |
| Fraud Ops Sync | Weekly | Fraud Ops, Eng, Product | Queue volume, tool feedback |
| Metrics Review | Weekly | Product, Finance, Fraud Ops | KPI dashboard review |
| Architecture Review | Monthly | Eng, SRE, Security | Scaling, reliability |
| Exec Update | Monthly | VP+, Product Lead | Summary, risks, asks |

### Escalation Path

```
Severity 1 (Revenue Impact):
  → Immediate: On-call Eng + SRE
  → 15 min: Eng Lead + Product
  → 30 min: VP Eng + VP Product
  → 1 hour: C-level if unresolved

Severity 2 (Metric Degradation):
  → Immediate: On-call Eng
  → 1 hour: Eng Lead + Fraud Ops
  → 4 hours: Product Lead
  → 24 hours: VP if unresolved

Severity 3 (Non-urgent):
  → Next business day review
  → Track in sprint backlog
```

---

## Risk Mitigation Matrix

### Technical Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Redis cluster failure | Low | Critical | Multi-AZ, fallback to cached | SRE |
| ML model degradation | Medium | High | PSI monitoring, auto-rollback | DS/ML |
| Feature pipeline lag | Medium | Medium | Staleness alerts, graceful degradation | Eng |
| Policy misconfiguration | Medium | High | Replay testing, staged rollout | Eng |
| Integration timeout | Low | Medium | Circuit breaker, async retry | Eng |

### Operational Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Analyst queue backup | Medium | Medium | Auto-routing rules, hiring plan | Fraud Ops |
| Threshold drift | High | Medium | Weekly threshold review, automation | DS/ML |
| Attack pattern shift | High | Medium | Champion/challenger experiments | DS/ML |
| Evidence gaps | Low | High | Schema validation, monitoring | Eng |
| Compliance audit finding | Low | High | Pre-audit review, documentation | Security |

### Business Risks

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Approval rate drop | Medium | Critical | Guard rails, rollback plan | Product |
| False positive spike | Medium | High | Customer feedback loop, monitoring | Product |
| Fraud loss spike | Low | Critical | Safe mode, rapid threshold adjustment | Fraud Ops |
| Customer churn | Low | High | FP tracking, win-back process | Product |

---

## Success Metrics and Governance

### Phase 1 Success Criteria (Go/No-Go)

| Metric | Target | Measurement | Owner |
|--------|--------|-------------|-------|
| P99 Latency | <200ms | Prometheus | Eng |
| Error Rate | <0.1% | Prometheus | Eng |
| Approval Rate Delta | >-2% | A/B comparison | Product |
| Fraud Detection Rate | >-5% | Historical replay | DS/ML |
| Load Test | 1000+ RPS | Locust | Eng |
| Test Coverage | 70%+ | CI/CD | Eng |

### Ongoing Governance

| Metric | Alert Threshold | Review Cadence | Escalation |
|--------|-----------------|----------------|------------|
| Approval Rate | <90% | Daily | Product Lead |
| Block Rate | >8% | Daily | Fraud Ops Lead |
| P99 Latency | >150ms | Real-time | On-call Eng |
| Fraud Rate | >1.5% | Weekly | Finance |
| Dispute Win Rate | <35% | Monthly | Legal |
| Manual Review % | >5% | Weekly | Fraud Ops |

---

## Key TPM Artifacts

### Documents I Would Produce

1. **Technical Requirements Document (TRD)** - Detailed specifications for each component
2. **Integration Runbook** - Step-by-step PSP integration guide
3. **Rollout Plan** - Week-by-week execution schedule with gates
4. **Risk Register** - Living document of risks and mitigations
5. **Metrics Dashboard Spec** - KPI definitions and visualization requirements
6. **Incident Response Playbook** - Severity definitions and response procedures
7. **Post-Launch Review Template** - Structured retrospective format

### Meetings I Would Run

1. **Architecture Review** - Cross-functional technical decision forum
2. **Rollout Readiness Review** - Go/no-go checklist walkthrough
3. **Weekly Metrics Review** - KPI trends and action items
4. **Incident Post-Mortem** - Structured learning from failures
5. **Quarterly Business Review** - Executive summary with ROI analysis

---

## Interview Application

**When asked "How would you drive this as a Principal TPM?":**

> "I'd start by mapping the stakeholder landscape - PSP integration, Security compliance, DS/ML model development, SRE reliability, Finance ROI, Product experience, and Fraud Ops usability. Each has different concerns that need to be balanced.
>
> For execution, I'd sequence the rollout to minimize risk: shadow mode first to validate accuracy and latency without customer impact, then 5% traffic with kill switch ready, then gradual ramp with business sign-off at each gate.
>
> The key decision frameworks center on three trade-offs: risk vs approval rate (expected value analysis), detection speed vs accuracy (latency budget), and automation vs manual review (confidence-based routing). I'd ensure these frameworks are documented and owned by the right stakeholders.
>
> Safety rails are non-negotiable: latency breakers, error rate breakers, approval rate guards. Safe mode behavior is pre-defined so we degrade gracefully rather than fail catastrophically.
>
> Communication is structured: daily standups for execution, weekly metrics reviews with business, monthly exec updates. Escalation paths are clear before we need them."

---

*This document demonstrates Principal TPM execution thinking: stakeholder management, decision frameworks, risk-aware sequencing, and structured governance.*

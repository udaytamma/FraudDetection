"""
Fraud Detection API

FastAPI application providing the main decision endpoint.
Designed for <200ms end-to-end latency.

Endpoints:
- POST /decide: Make fraud decision for a transaction
- GET /health: Health check
- GET /metrics: Prometheus metrics
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request, Depends

logger = logging.getLogger("fraud_detection.api")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..config import settings
from ..schemas import PaymentEvent, FraudDecisionResponse, Decision, RiskScores, FeatureSet, ChargebackRequest, RefundRequest
from ..features import FeatureStore
from ..scoring import RiskScorer
from ..policy import (
    PolicyEngine,
    PolicyVersioningService,
    PolicyValidationError,
    ThresholdUpdate,
    RuleUpdate,
    ListUpdate,
)
from ..evidence import EvidenceService
from ..metrics import metrics, setup_metrics, telemetry
from ..ml import ModelMonitor
from .dependencies import get_redis, get_db_pool
from .auth import require_api_token, require_admin_token, require_metrics_token


# Global instances (initialized in lifespan)
redis_client: Optional[redis.Redis] = None
feature_store: Optional[FeatureStore] = None
risk_scorer: Optional[RiskScorer] = None
policy_engine: Optional[PolicyEngine] = None
evidence_service: Optional[EvidenceService] = None
policy_versioning: Optional[PolicyVersioningService] = None
model_monitor: Optional[ModelMonitor] = None

CRIMINAL_REASON_CODES = {"10.1", "10.2", "10.3", "10.4", "10.5"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Initializes and cleans up resources:
    - Redis connection
    - Database pool
    - Service instances
    """
    global redis_client, feature_store, risk_scorer, policy_engine, evidence_service, policy_versioning, model_monitor

    # Initialize Redis
    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True,
    )

    # Verify Redis connection
    try:
        await redis_client.ping()
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)
        # Continue without Redis for testing

    # Initialize services
    feature_store = FeatureStore(redis_client)
    risk_scorer = RiskScorer()
    model_monitor = ModelMonitor(metrics_enabled=settings.metrics_enabled)

    # Load policy from file if exists
    policy_path = Path(__file__).parent.parent.parent / "config" / "policy.yaml"
    policy_engine = PolicyEngine(policy_path=policy_path)

    # Initialize evidence service
    evidence_service = EvidenceService(settings.postgres_url)
    await evidence_service.initialize()

    # Initialize policy versioning service
    policy_versioning = PolicyVersioningService(
        database_url=settings.postgres_url,
        policy_path=policy_path,
    )
    await policy_versioning.initialize()

    # Setup metrics
    if settings.metrics_enabled:
        setup_metrics()

    yield

    # Cleanup
    if redis_client:
        await redis_client.aclose()
    if evidence_service:
        await evidence_service.close()
    if policy_versioning:
        await policy_versioning.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Fraud Detection API",
        description="Real-time fraud detection for payment transactions",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns service health status and component availability.
    """
    health = {
        "status": "healthy",
        "components": {
            "redis": False,
            "postgres": False,
            "policy": False,
        }
    }

    # Check Redis
    try:
        if redis_client:
            await redis_client.ping()
            health["components"]["redis"] = True
    except Exception:
        pass

    # Check policy engine
    if policy_engine:
        health["components"]["policy"] = True
        health["policy_version"] = policy_engine.version

    # Check Postgres
    if evidence_service:
        try:
            await evidence_service.health_check()
            health["components"]["postgres"] = True
        except Exception:
            pass

    # Overall status
    if not all(health["components"].values()):
        health["status"] = "degraded"

    return health


@app.get("/metrics")
def metrics_endpoint(_: None = Depends(require_metrics_token)):
    """Expose Prometheus metrics with optional token auth."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/metrics/summary")
def metrics_summary(hours: int = 24, _: None = Depends(require_metrics_token)):
    """Return recent decision telemetry for dashboards."""
    return telemetry.snapshot(hours=hours)


@app.post("/decide", response_model=FraudDecisionResponse)
async def make_decision(
    event: PaymentEvent,
    request: Request,
    _: None = Depends(require_api_token),
):
    """
    Make a fraud decision for a payment transaction.

    This is the primary endpoint for real-time fraud detection.
    Target latency: <200ms end-to-end.

    Args:
        event: Payment event to evaluate

    Returns:
        FraudDecisionResponse with decision and supporting data
    """
    start_time = time.perf_counter()

    try:
        # Track request
        metrics.requests_total.labels(endpoint="/decide").inc()

        # Safe mode: bypass decisioning for controlled fallback
        if settings.safe_mode_enabled:
            safe_time = (time.perf_counter() - start_time) * 1000
            response = _safe_mode_response(event, safe_time)

            # Record Prometheus metrics for SLO monitoring
            metrics.decisions_total.labels(decision=response.decision.value).inc()
            metrics.e2e_latency.observe(safe_time)
            telemetry.record(response.decision.value, safe_time)
            if model_monitor:
                model_monitor.record_decision(response.decision, response.scores)

            # Capture evidence for auditability (zeroed scores, no computed features)
            safe_features = FeatureSet()
            _fire_and_forget(
                evidence_service.capture_evidence(
                    event, safe_features, response.scores, response,
                    policy_version_id=None,
                ),
                "safe_mode_evidence",
            )

            return response

        # =======================================================================
        # Step 1: Check idempotency (return cached result if exists)
        # =======================================================================
        cached_result = await _check_idempotency(event.idempotency_key)
        if cached_result:
            metrics.cache_hits.inc()
            return cached_result

        # =======================================================================
        # Step 2: Compute features
        # =======================================================================
        feature_start = time.perf_counter()
        features = await feature_store.compute_features(event)
        feature_time = (time.perf_counter() - feature_start) * 1000

        # Track feature latency
        metrics.feature_latency.observe(feature_time)

        # =======================================================================
        # Step 3: Compute risk scores
        # =======================================================================
        scoring_start = time.perf_counter()
        scores, score_reasons = await risk_scorer.compute_scores(event, features)
        scoring_time = (time.perf_counter() - scoring_start) * 1000

        # Track scoring latency
        metrics.scoring_latency.observe(scoring_time)

        # =======================================================================
        # Step 4: Evaluate policy
        # =======================================================================
        policy_start = time.perf_counter()
        decision, policy_reasons, friction_type, review_priority = policy_engine.evaluate(
            event, features, scores
        )
        policy_time = (time.perf_counter() - policy_start) * 1000

        # Track policy latency
        metrics.policy_latency.observe(policy_time)

        # Combine reasons
        all_reasons = score_reasons + policy_reasons

        # =======================================================================
        # Step 5: Build response
        # =======================================================================
        total_time = (time.perf_counter() - start_time) * 1000

        response = FraudDecisionResponse(
            transaction_id=event.transaction_id,
            idempotency_key=event.idempotency_key,
            decision=decision,
            reasons=all_reasons,
            scores=scores,
            friction_type=friction_type,
            friction_message=_get_friction_message(friction_type) if friction_type else None,
            review_priority=review_priority,
            review_notes=_get_review_notes(all_reasons) if review_priority else None,
            processing_time_ms=round(total_time, 2),
            feature_time_ms=round(feature_time, 2),
            scoring_time_ms=round(scoring_time, 2),
            policy_time_ms=round(policy_time, 2),
            policy_version=policy_engine.version,
            is_cached=False,
        )

        # =======================================================================
        # Step 6: Update entity profiles (async, don't block response)
        # =======================================================================
        is_decline = decision == Decision.BLOCK
        _fire_and_forget(
            feature_store.update_entity_profiles(event, is_decline),
            "update_entity_profiles",
        )

        # =======================================================================
        # Step 7: Capture evidence (async)
        # =======================================================================
        policy_version_id = policy_versioning.current_version_id if policy_versioning else None
        _fire_and_forget(
            evidence_service.capture_evidence(
                event, features, scores, response, policy_version_id=policy_version_id
            ),
            "capture_evidence",
        )

        # =======================================================================
        # Step 8: Persist idempotency record + cache result
        # =======================================================================
        await _persist_idempotency(event.idempotency_key, response)
        await _cache_result(event.idempotency_key, response)

        # Track metrics
        metrics.decisions_total.labels(decision=decision.value).inc()
        metrics.e2e_latency.observe(total_time)
        telemetry.record(decision.value, total_time)
        if model_monitor:
            model_monitor.record_decision(decision, scores)

        # Log slow requests
        if total_time > settings.target_e2e_latency_ms:
            metrics.slow_requests.inc()

        return response

    except Exception as e:
        metrics.errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


async def _check_idempotency(idempotency_key: str) -> Optional[FraudDecisionResponse]:
    """Check if we've already processed this request."""
    if redis_client:
        try:
            key = f"{settings.redis_key_prefix}idempotency:{idempotency_key}"
            cached = await redis_client.get(key)
            if cached:
                import json
                data = json.loads(cached)
                response = FraudDecisionResponse(**data)
                response.is_cached = True
                return response
        except Exception:
            pass

    if evidence_service:
        try:
            record = await evidence_service.get_idempotency_response(idempotency_key)
            if record:
                response = FraudDecisionResponse(**record)
                response.is_cached = True
                return response
        except Exception:
            pass

    return None


async def _cache_result(idempotency_key: str, response: FraudDecisionResponse) -> None:
    """Cache the result for idempotency."""
    if not redis_client:
        return

    try:
        key = f"{settings.redis_key_prefix}idempotency:{idempotency_key}"
        # Cache for 24 hours
        await redis_client.setex(
            key,
            86400,
            response.model_dump_json(),
        )
    except Exception:
        pass


async def _persist_idempotency(idempotency_key: str, response: FraudDecisionResponse) -> None:
    """Persist idempotency response in Postgres (fallback for Redis)."""
    if not evidence_service:
        return
    try:
        await evidence_service.store_idempotency_response(
            idempotency_key,
            response.model_dump(),
            ttl_hours=settings.idempotency_ttl_hours,
        )
    except Exception as e:
        logger.warning("Idempotency persistence failed: %s", e)


def _get_friction_message(friction_type: str) -> str:
    """Get user-facing message for friction type."""
    messages = {
        "3DS": "Additional verification required. You will be redirected to your bank.",
        "OTP": "Please enter the verification code sent to your phone.",
        "STEP_UP": "Please verify your identity to continue.",
        "CAPTCHA": "Please complete the verification challenge.",
    }
    return messages.get(friction_type, "Additional verification required.")


def _get_review_notes(reasons: list) -> str:
    """Generate review notes from decision reasons."""
    if not reasons:
        return "No specific concerns noted."

    high_severity = [r for r in reasons if r.severity in ("HIGH", "CRITICAL")]
    if high_severity:
        return "; ".join(r.description for r in high_severity[:3])

    return "; ".join(r.description for r in reasons[:3])


def _safe_mode_response(event: PaymentEvent, elapsed_ms: float = 0.0) -> FraudDecisionResponse:
    """Return a deterministic response when safe mode is enabled."""
    decision = Decision[settings.safe_mode_decision]
    response = FraudDecisionResponse(
        transaction_id=event.transaction_id,
        idempotency_key=event.idempotency_key,
        decision=decision,
        reasons=[],
        scores=RiskScores(risk_score=0.0, criminal_score=0.0, friendly_fraud_score=0.0),
        friction_type=None,
        friction_message=None,
        review_priority=None,
        review_notes=None,
        processing_time_ms=round(elapsed_ms, 2),
        feature_time_ms=0.0,
        scoring_time_ms=0.0,
        policy_time_ms=0.0,
        policy_version=policy_engine.version if policy_engine else "unknown",
        is_cached=False,
    )
    return response


def _fire_and_forget(coro, name: str) -> None:
    """Run a coroutine in the background and log failures."""
    task = asyncio.create_task(coro)

    def _log_exception(task_ref: asyncio.Task) -> None:
        try:
            task_ref.result()
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.warning("Background task %s failed: %s", name, exc)

    task.add_done_callback(_log_exception)


@app.get("/policy/version")
async def get_policy_version(_: None = Depends(require_api_token)):
    """Get current policy version and hash."""
    return {
        "version": policy_engine.version,
        "hash": policy_engine.hash,
    }


@app.post("/policy/reload")
async def reload_policy(_: None = Depends(require_admin_token)):
    """Reload policy from configuration file."""
    if policy_engine.reload_policy():
        return {
            "status": "success",
            "version": policy_engine.version,
            "hash": policy_engine.hash,
        }
    else:
        raise HTTPException(status_code=500, detail="Policy reload failed")


# =============================================================================
# POLICY MANAGEMENT ENDPOINTS
# =============================================================================

@app.get("/policy")
async def get_policy(_: None = Depends(require_api_token)):
    """Get the current active policy configuration."""
    version = await policy_versioning.get_active_version()
    if not version:
        raise HTTPException(status_code=404, detail="No active policy found")

    return {
        "version": version.version,
        "policy_hash": version.policy_hash,
        "changed_by": version.changed_by,
        "created_at": version.created_at.isoformat(),
        "policy": version.policy_content,
    }


@app.get("/policy/versions")
async def list_policy_versions(limit: int = 50, _: None = Depends(require_api_token)):
    """List all policy versions, most recent first."""
    versions = await policy_versioning.list_versions(limit=limit)
    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "change_type": v.change_type,
                "change_summary": v.change_summary,
                "changed_by": v.changed_by,
                "created_at": v.created_at.isoformat(),
                "is_active": v.is_active,
            }
            for v in versions
        ]
    }


@app.get("/policy/versions/{version}")
async def get_policy_version(version: str, _: None = Depends(require_api_token)):
    """Get a specific policy version."""
    v = await policy_versioning.get_version(version)
    if not v:
        raise HTTPException(status_code=404, detail=f"Version '{version}' not found")

    return {
        "id": v.id,
        "version": v.version,
        "policy_hash": v.policy_hash,
        "change_type": v.change_type,
        "change_summary": v.change_summary,
        "changed_by": v.changed_by,
        "created_at": v.created_at.isoformat(),
        "is_active": v.is_active,
        "previous_version": v.previous_version,
        "policy": v.policy_content,
    }


@app.put("/policy/thresholds")
async def update_thresholds(
    updates: list[ThresholdUpdate],
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """
    Update score thresholds.

    Validates that friction < review < block for each score type.
    """
    try:
        version = await policy_versioning.update_thresholds(updates, changed_by=changed_by)

        # Reload policy engine with new config
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/policy/rules")
async def add_rule(
    rule: RuleUpdate,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """Add a new policy rule."""
    try:
        version = await policy_versioning.add_rule(rule, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/policy/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    rule: RuleUpdate,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """Update an existing policy rule."""
    if rule.id != rule_id:
        raise HTTPException(status_code=400, detail="Rule ID in path must match body")

    try:
        version = await policy_versioning.update_rule(rule, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/policy/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """Delete a policy rule."""
    try:
        version = await policy_versioning.delete_rule(rule_id, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/policy/lists/{list_type}")
async def add_to_list(
    list_type: str,
    value: str,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """Add a value to a blocklist or allowlist."""
    try:
        update = ListUpdate(list_type=list_type, value=value, action="add")
        version = await policy_versioning.update_list(update, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/policy/lists/{list_type}/{value}")
async def remove_from_list(
    list_type: str,
    value: str,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """Remove a value from a blocklist or allowlist."""
    try:
        update = ListUpdate(list_type=list_type, value=value, action="remove")
        version = await policy_versioning.update_list(update, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/policy/rollback/{target_version}")
async def rollback_policy(
    target_version: str,
    changed_by: str = "system",
    _: None = Depends(require_admin_token),
):
    """
    Rollback to a previous policy version.

    Creates a new version with the content from the target version.
    Does not delete any history.
    """
    try:
        version = await policy_versioning.rollback(target_version, changed_by=changed_by)

        # Reload policy engine
        policy_engine.reload_policy()

        return {
            "status": "success",
            "version": version.version,
            "change_summary": version.change_summary,
            "rolled_back_from": target_version,
        }
    except PolicyValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/policy/diff/{version1}/{version2}")
async def diff_policy_versions(
    version1: str,
    version2: str,
    _: None = Depends(require_api_token),
):
    """Compare two policy versions and return differences."""
    v1 = await policy_versioning.get_version(version1)
    v2 = await policy_versioning.get_version(version2)

    if not v1:
        raise HTTPException(status_code=404, detail=f"Version '{version1}' not found")
    if not v2:
        raise HTTPException(status_code=404, detail=f"Version '{version2}' not found")

    # Simple diff - compare JSON structures
    diff = {
        "version1": version1,
        "version2": version2,
        "changes": [],
    }

    # Compare thresholds
    t1 = v1.policy_content.get("thresholds", {})
    t2 = v2.policy_content.get("thresholds", {})
    for key in set(t1.keys()) | set(t2.keys()):
        if t1.get(key) != t2.get(key):
            diff["changes"].append({
                "type": "threshold",
                "key": key,
                "v1": t1.get(key),
                "v2": t2.get(key),
            })

    # Compare rules
    r1 = {r["id"]: r for r in v1.policy_content.get("rules", [])}
    r2 = {r["id"]: r for r in v2.policy_content.get("rules", [])}
    for key in set(r1.keys()) | set(r2.keys()):
        if key not in r1:
            diff["changes"].append({"type": "rule_added", "key": key, "v2": r2[key]})
        elif key not in r2:
            diff["changes"].append({"type": "rule_removed", "key": key, "v1": r1[key]})
        elif r1[key] != r2[key]:
            diff["changes"].append({"type": "rule_modified", "key": key, "v1": r1[key], "v2": r2[key]})

    # Compare lists
    for list_name in ['blocklist_cards', 'blocklist_devices', 'blocklist_ips',
                      'blocklist_users', 'allowlist_cards', 'allowlist_users',
                      'allowlist_services']:
        l1 = set(v1.policy_content.get(list_name, []))
        l2 = set(v2.policy_content.get(list_name, []))
        added = l2 - l1
        removed = l1 - l2
        if added or removed:
            diff["changes"].append({
                "type": "list",
                "key": list_name,
                "added": list(added),
                "removed": list(removed),
            })

    return diff


# =============================================================================
# CHARGEBACK INGESTION ENDPOINT
# =============================================================================

@app.post("/chargebacks")
async def ingest_chargeback(
    chargeback: ChargebackRequest,
    _: None = Depends(require_api_token),
):
    """
    Ingest a chargeback notification.

    Records the chargeback in PostgreSQL and updates entity risk profiles
    in Redis so that future transactions reflect chargeback history.
    """
    # 1. Record chargeback in Postgres
    record_id = await evidence_service.record_chargeback(
        transaction_id=chargeback.transaction_id,
        chargeback_id=chargeback.chargeback_id,
        amount_cents=chargeback.amount_cents,
        reason_code=chargeback.reason_code,
        reason_description=chargeback.reason_description,
        fraud_type=chargeback.fraud_type,
    )

    if not record_id:
        raise HTTPException(status_code=500, detail="Failed to record chargeback")

    # 2. Look up original transaction to find affected entities
    evidence = await evidence_service.get_evidence(chargeback.transaction_id)

    # 3. Update entity profiles in Redis with chargeback signal
    if evidence:
        _fire_and_forget(
            feature_store.update_chargeback_profiles(
                card_token=evidence.get("card_token"),
                user_id=evidence.get("user_id"),
                device_id_hash=evidence.get("device_id_hash"),
                ip_address_hash=evidence.get("ip_address_hash"),
            ),
            "update_chargeback_profiles",
        )
        if model_monitor:
            is_fraud = chargeback.fraud_type == "CRIMINAL" or chargeback.reason_code in CRIMINAL_REASON_CODES
            model_monitor.record_outcome(evidence.get("model_variant"), is_fraud)

    return {
        "status": "success",
        "record_id": record_id,
        "profiles_updated": evidence is not None,
    }


# =============================================================================
# REFUND INGESTION ENDPOINT
# =============================================================================

@app.post("/refunds")
async def ingest_refund(
    refund: RefundRequest,
    _: None = Depends(require_api_token),
):
    """
    Ingest a refund notification.

    Records the refund in PostgreSQL and updates user profiles in Redis
    so that friendly-fraud scoring reflects refund history.
    """
    record_id = await evidence_service.record_refund(
        transaction_id=refund.transaction_id,
        refund_id=refund.refund_id,
        amount_cents=refund.amount_cents,
        reason_code=refund.reason_code,
        reason_description=refund.reason_description,
    )

    if not record_id:
        raise HTTPException(status_code=500, detail="Failed to record refund")

    evidence = await evidence_service.get_evidence(refund.transaction_id)

    if evidence:
        _fire_and_forget(
            feature_store.update_refund_profiles(
                user_id=evidence.get("user_id"),
            ),
            "update_refund_profiles",
        )

    return {
        "status": "success",
        "record_id": record_id,
        "profiles_updated": evidence is not None,
    }


# Entry point for running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_debug,
    )

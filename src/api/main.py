"""
Fraud Detection API

FastAPI application providing the main decision endpoint.
Designed for <200ms end-to-end latency.

Endpoints:
- POST /decide: Make fraud decision for a transaction
- GET /health: Health check
- GET /metrics: Prometheus metrics
"""

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas import PaymentEvent, FraudDecisionResponse, Decision
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
from ..metrics import metrics, setup_metrics
from .dependencies import get_redis, get_db_pool


# Global instances (initialized in lifespan)
redis_client: Optional[redis.Redis] = None
feature_store: Optional[FeatureStore] = None
risk_scorer: Optional[RiskScorer] = None
policy_engine: Optional[PolicyEngine] = None
evidence_service: Optional[EvidenceService] = None
policy_versioning: Optional[PolicyVersioningService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Initializes and cleans up resources:
    - Redis connection
    - Database pool
    - Service instances
    """
    global redis_client, feature_store, risk_scorer, policy_engine, evidence_service, policy_versioning

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
        print(f"WARNING: Redis connection failed: {e}")
        # Continue without Redis for testing

    # Initialize services
    feature_store = FeatureStore(redis_client)
    risk_scorer = RiskScorer()

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
        allow_origins=["*"],  # Configure appropriately for production
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


@app.post("/decide", response_model=FraudDecisionResponse)
async def make_decision(event: PaymentEvent, request: Request):
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
        # Fire and forget - update profiles in background
        await feature_store.update_entity_profiles(event, is_decline)

        # =======================================================================
        # Step 7: Capture evidence (async)
        # =======================================================================
        # Get policy version ID for evidence linkage
        policy_version_id = policy_versioning.current_version_id if policy_versioning else None
        await evidence_service.capture_evidence(
            event, features, scores, response, policy_version_id=policy_version_id
        )

        # =======================================================================
        # Step 8: Cache result for idempotency
        # =======================================================================
        await _cache_result(event.idempotency_key, response)

        # Track metrics
        metrics.decisions_total.labels(decision=decision.value).inc()
        metrics.e2e_latency.observe(total_time)

        # Log slow requests
        if total_time > settings.target_e2e_latency_ms:
            metrics.slow_requests.inc()

        return response

    except Exception as e:
        metrics.errors_total.labels(error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=str(e))


async def _check_idempotency(idempotency_key: str) -> Optional[FraudDecisionResponse]:
    """Check if we've already processed this request."""
    if not redis_client:
        return None

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


@app.get("/policy/version")
async def get_policy_version():
    """Get current policy version and hash."""
    return {
        "version": policy_engine.version,
        "hash": policy_engine.hash,
    }


@app.post("/policy/reload")
async def reload_policy():
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
async def get_policy():
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
async def list_policy_versions(limit: int = 50):
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
async def get_policy_version(version: str):
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
async def update_thresholds(updates: list[ThresholdUpdate], changed_by: str = "system"):
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
async def add_rule(rule: RuleUpdate, changed_by: str = "system"):
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
async def update_rule(rule_id: str, rule: RuleUpdate, changed_by: str = "system"):
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
async def delete_rule(rule_id: str, changed_by: str = "system"):
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
async def add_to_list(list_type: str, value: str, changed_by: str = "system"):
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
async def remove_from_list(list_type: str, value: str, changed_by: str = "system"):
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
async def rollback_policy(target_version: str, changed_by: str = "system"):
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
async def diff_policy_versions(version1: str, version2: str):
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


# Entry point for running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_debug,
    )

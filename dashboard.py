"""
Telco/MSP Payment Fraud Detection Platform - Demo Dashboard

Professional-grade Streamlit dashboard for demonstrating and testing
the fraud detection system for Telco/MSP payment fraud.

Note: This dashboard uses raw asyncpg for direct read-only analytics queries
to PostgreSQL, rather than SQLAlchemy. This is intentional -- the dashboard is a
standalone visualization tool, not a transactional application, so the simpler
asyncpg interface is appropriate for read-only aggregate queries.

Supports:
- Mobile: SIM activation, topup, device upgrade, SIM swap, international enable
- Broadband: Service activation, equipment swap, speed upgrade, equipment purchase

Run: streamlit run dashboard.py --server.port 8501
"""

import asyncio
import json
import os
import subprocess
import signal
import time
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import asyncpg

# Page configuration
st.set_page_config(
    page_title="Telco Payment Fraud Detection",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configuration
API_URL = os.getenv("FRAUD_API_URL", "http://localhost:8000")
API_TOKEN = os.getenv("API_TOKEN", None)
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://fraud_user:fraud_dev_password@localhost:5432/fraud_detection"
)

def _api_headers() -> dict[str, str]:
    """Build auth headers for API requests."""
    if API_TOKEN:
        return {"X-API-Key": API_TOKEN}
    return {}

# Dark-mode color constants for Plotly (CSS can't reach Plotly's SVG canvas)
_DARK_BG = "#1e293b"
_DARK_BORDER = "#334155"
_DARK_TEXT = "#e2e8f0"
_DARK_MUTED = "#94a3b8"

# Custom CSS for dark-mode styling
st.markdown("""
<style>

    /* Main container styling */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    /* Status indicators */
    .status-healthy { color: #10b981; font-weight: 600; }
    .status-degraded { color: #f59e0b; font-weight: 600; }
    .status-down { color: #ef4444; font-weight: 600; }

    /* Decision badges - white text on colored bg, works in both modes */
    .decision-allow {
        background-color: #10b981; color: white;
        padding: 0.5rem 1rem; border-radius: 9999px;
        font-weight: 600; display: inline-block;
    }
    .decision-friction {
        background-color: #f59e0b; color: white;
        padding: 0.5rem 1rem; border-radius: 9999px;
        font-weight: 600; display: inline-block;
    }
    .decision-review {
        background-color: #f97316; color: white;
        padding: 0.5rem 1rem; border-radius: 9999px;
        font-weight: 600; display: inline-block;
    }
    .decision-block {
        background-color: #ef4444; color: white;
        padding: 0.5rem 1rem; border-radius: 9999px;
        font-weight: 600; display: inline-block;
    }

    /* Severity badges */
    .severity-critical {
        background-color: #7f1d1d; color: white;
        padding: 0.25rem 0.5rem; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
    }
    .severity-high {
        background-color: #ef4444; color: white;
        padding: 0.25rem 0.5rem; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
    }
    .severity-medium {
        background-color: #f59e0b; color: white;
        padding: 0.25rem 0.5rem; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
    }
    .severity-low {
        background-color: #6b7280; color: white;
        padding: 0.25rem 0.5rem; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
    }

    /* Score gauge styling */
    .score-container { text-align: center; padding: 1rem; }

    /* Reason card */
    .reason-card {
        background-color: #1e293b;
        border-left: 4px solid #ef4444;
        padding: 1rem; margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }

    /* Header styling */
    .dashboard-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #1e40af 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1rem;
        border: 1px solid rgba(59, 130, 246, 0.2);
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    }
    .dashboard-header h1 {
        margin: 0; font-size: 1.75rem; font-weight: 700;
        letter-spacing: -0.02em;
    }
    .dashboard-header .subtitle {
        margin: 0.5rem 0 0 0; opacity: 0.85; font-size: 0.95rem;
        line-height: 1.5; max-width: 700px;
    }
    .dashboard-header .tech-pills {
        margin-top: 0.75rem; display: flex; gap: 0.5rem; flex-wrap: wrap;
    }
    .dashboard-header .tech-pill {
        background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15);
        padding: 0.25rem 0.75rem; border-radius: 9999px;
        font-size: 0.75rem; font-weight: 500; color: rgba(255,255,255,0.9);
    }

    /* Tab intro banner */
    .tab-intro {
        background: linear-gradient(90deg, rgba(59,130,246,0.08) 0%, rgba(59,130,246,0.02) 100%);
        border-left: 3px solid #3b82f6;
        padding: 0.75rem 1rem;
        margin-bottom: 1.25rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.9rem;
        color: #cbd5e1;
        line-height: 1.5;
    }

    /* Quick Guide styles are inline via st.html() -- no global CSS needed */

    /* Metric box */
    .metric-box {
        background-color: #1e293b; border: 1px solid #334155;
        border-radius: 8px; padding: 1rem; text-align: center;
    }

    /* Decision history table */
    .styled-table {
        width: 100%; border-collapse: collapse; font-size: 0.85rem;
    }
    .styled-table th {
        background-color: #1e293b; color: #94a3b8;
        text-transform: uppercase; font-size: 0.75rem;
        letter-spacing: 0.05em; padding: 0.6rem 0.75rem;
        text-align: left; border-bottom: 2px solid #334155;
    }
    .styled-table td {
        padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b;
        color: #e2e8f0;
    }
    .styled-table tr:hover td {
        background-color: rgba(59, 130, 246, 0.08);
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Tab styling - professional look */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #0f172a;
        padding: 4px;
        border-radius: 12px;
        border: 1px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #94a3b8;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        font-size: 0.85rem;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #e2e8f0;
        background-color: rgba(59, 130, 246, 0.1);
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e3a5f !important;
        color: white !important;
        font-weight: 600;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* Empty state styling */
    .empty-state {
        text-align: center; padding: 3rem 2rem;
        color: #64748b;
    }
    .empty-state-icon { font-size: 2.5rem; margin-bottom: 1rem; }
    .empty-state-title {
        font-size: 1.1rem; font-weight: 600; color: #94a3b8;
        margin-bottom: 0.5rem;
    }
    .empty-state-desc { font-size: 0.9rem; max-width: 400px; margin: 0 auto; }

    /* Sidebar polish */
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #1e293b;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Helper Functions
# ============================================================================

def get_api_health() -> dict:
    """Check API health status."""
    try:
        response = httpx.get(f"{API_URL}/health", headers=_api_headers(), timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"status": "down", "components": {"redis": False, "postgres": False, "policy": False}}


def get_policy_version() -> dict:
    """Get current policy version."""
    try:
        response = httpx.get(f"{API_URL}/policy/version", headers=_api_headers(), timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"version": "N/A", "hash": "N/A"}


def get_current_policy() -> dict:
    """Get current active policy configuration."""
    try:
        response = httpx.get(f"{API_URL}/policy", headers=_api_headers(), timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {}


def get_policy_versions(limit: int = 50) -> list:
    """Get policy version history."""
    try:
        response = httpx.get(f"{API_URL}/policy/versions", params={"limit": limit}, headers=_api_headers(), timeout=5.0)
        if response.status_code == 200:
            return response.json().get("versions", [])
    except Exception:
        pass
    return []


def update_thresholds(updates: list, changed_by: str = "dashboard") -> dict:
    """Update score thresholds."""
    try:
        response = httpx.put(
            f"{API_URL}/policy/thresholds",
            json=updates,
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def add_policy_rule(rule: dict, changed_by: str = "dashboard") -> dict:
    """Add a new policy rule."""
    try:
        response = httpx.post(
            f"{API_URL}/policy/rules",
            json=rule,
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def update_policy_rule(rule_id: str, rule: dict, changed_by: str = "dashboard") -> dict:
    """Update an existing policy rule."""
    try:
        response = httpx.put(
            f"{API_URL}/policy/rules/{rule_id}",
            json=rule,
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def delete_policy_rule(rule_id: str, changed_by: str = "dashboard") -> dict:
    """Delete a policy rule."""
    try:
        response = httpx.delete(
            f"{API_URL}/policy/rules/{rule_id}",
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def add_to_policy_list(list_type: str, value: str, changed_by: str = "dashboard") -> dict:
    """Add a value to blocklist or allowlist."""
    try:
        response = httpx.post(
            f"{API_URL}/policy/lists/{list_type}",
            params={"value": value, "changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def remove_from_policy_list(list_type: str, value: str, changed_by: str = "dashboard") -> dict:
    """Remove a value from blocklist or allowlist."""
    try:
        response = httpx.delete(
            f"{API_URL}/policy/lists/{list_type}/{value}",
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def rollback_policy(target_version: str, changed_by: str = "dashboard") -> dict:
    """Rollback to a previous policy version."""
    try:
        response = httpx.post(
            f"{API_URL}/policy/rollback/{target_version}",
            params={"changed_by": changed_by},
            headers=_api_headers(),
            timeout=10.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def submit_transaction(payload: dict) -> dict:
    """Submit a transaction for fraud decision."""
    try:
        response = httpx.post(
            f"{API_URL}/decide",
            json=payload,
            headers=_api_headers(),
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}


def get_model_registry() -> dict:
    """Read model registry JSON for dashboard display."""
    registry_path = os.path.join(os.path.dirname(__file__), "models", "registry.json")
    try:
        with open(registry_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


async def get_ml_analytics(window_hours: int | None = 24) -> dict:
    """Get ML-specific analytics from PostgreSQL.

    Args:
        window_hours: Number of hours to look back. None means all time.
    """
    try:
        conn = await asyncpg.connect(POSTGRES_URL)

        if window_hours is not None:
            where_clause = f"WHERE captured_at > NOW() - INTERVAL '{window_hours} hours'"
            where_and = f"WHERE ml_score IS NOT NULL AND captured_at > NOW() - INTERVAL '{window_hours} hours'"
        else:
            where_clause = ""
            where_and = "WHERE ml_score IS NOT NULL"

        # Variant distribution
        variant_dist = await conn.fetch(f"""
            SELECT
                COALESCE(model_variant, 'rules-only') as variant,
                COUNT(*) as count,
                AVG(ml_score) as avg_ml_score,
                AVG(risk_score) as avg_risk_score
            FROM transaction_evidence
            {where_clause}
            GROUP BY model_variant
            ORDER BY count DESC
        """)

        # ML score distribution (for histogram)
        ml_scores = await conn.fetch(f"""
            SELECT ml_score
            FROM transaction_evidence
            {where_and}
        """)

        # Decision by variant
        decision_by_variant = await conn.fetch(f"""
            SELECT
                COALESCE(model_variant, 'rules-only') as variant,
                decision,
                COUNT(*) as count
            FROM transaction_evidence
            {where_clause}
            GROUP BY model_variant, decision
            ORDER BY variant, decision
        """)

        # ML score vs rules score (for scatter plot)
        ml_vs_rules = await conn.fetch(f"""
            SELECT ml_score, criminal_score
            FROM transaction_evidence
            {where_and}
            LIMIT 2000
        """)

        # ML summary metrics
        ml_summary = await conn.fetch(f"""
            SELECT
                COUNT(*) as total,
                COUNT(ml_score) as ml_scored,
                AVG(CASE WHEN model_variant = 'champion' THEN ml_score END) as champion_avg,
                AVG(CASE WHEN model_variant = 'challenger' THEN ml_score END) as challenger_avg
            FROM transaction_evidence
            {where_clause}
        """)

        await conn.close()

        summary = dict(ml_summary[0]) if ml_summary else {}

        return {
            "variant_distribution": [dict(r) for r in variant_dist],
            "ml_scores": [float(r["ml_score"]) for r in ml_scores if r["ml_score"] is not None],
            "decision_by_variant": [dict(r) for r in decision_by_variant],
            "ml_vs_rules": [
                {"ml_score": float(r["ml_score"]), "criminal_score": float(r["criminal_score"])}
                for r in ml_vs_rules
                if r["ml_score"] is not None and r["criminal_score"] is not None
            ],
            "summary": {
                "total": summary.get("total", 0),
                "ml_scored": summary.get("ml_scored", 0),
                "champion_avg": float(summary["champion_avg"]) if summary.get("champion_avg") is not None else None,
                "challenger_avg": float(summary["challenger_avg"]) if summary.get("challenger_avg") is not None else None,
            },
        }
    except Exception as e:
        return {"error": str(e)}


async def get_decision_history(limit: int = 100) -> pd.DataFrame:
    """Query decision history from PostgreSQL."""
    try:
        conn = await asyncpg.connect(POSTGRES_URL)
        rows = await conn.fetch("""
            SELECT
                transaction_id,
                decision,
                risk_score,
                criminal_score,
                friendly_fraud_score,
                ml_score,
                model_variant,
                amount_cents,
                card_token,
                COALESCE(service_id, merchant_id) AS service_id,
                processing_time_ms,
                captured_at
            FROM transaction_evidence
            ORDER BY captured_at DESC
            LIMIT $1
        """, limit)
        await conn.close()

        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            return df
    except Exception as e:
        st.error(f"Database error: {e}")

    return pd.DataFrame()


async def get_analytics_data(window_hours: int | None = None) -> dict:
    """Get aggregated analytics data.

    Args:
        window_hours: Number of hours to look back. None means all time.
    """
    try:
        conn = await asyncpg.connect(POSTGRES_URL)

        if window_hours is not None:
            time_filter = f"WHERE captured_at > NOW() - INTERVAL '{window_hours} hours'"
        else:
            time_filter = ""

        # Decision distribution
        decision_dist = await conn.fetch(f"""
            SELECT decision, COUNT(*) as count
            FROM transaction_evidence
            {time_filter}
            GROUP BY decision
        """)

        # Hourly volume (always show recent window for chart readability)
        volume_filter = f"WHERE captured_at > NOW() - INTERVAL '{window_hours} hours'" if window_hours else "WHERE captured_at > NOW() - INTERVAL '168 hours'"
        hourly_volume = await conn.fetch(f"""
            SELECT
                DATE_TRUNC('hour', captured_at) as hour,
                COUNT(*) as count,
                AVG(processing_time_ms) as avg_latency
            FROM transaction_evidence
            {volume_filter}
            GROUP BY DATE_TRUNC('hour', captured_at)
            ORDER BY hour
        """)

        # Score distribution
        score_stats = await conn.fetchrow(f"""
            SELECT
                AVG(risk_score) as avg_risk,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY risk_score) as median_risk,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY risk_score) as p95_risk,
                AVG(processing_time_ms) as avg_latency,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY processing_time_ms) as p99_latency,
                COUNT(*) as total_count
            FROM transaction_evidence
            {time_filter}
        """)

        await conn.close()

        return {
            "decision_distribution": [dict(r) for r in decision_dist],
            "hourly_volume": [dict(r) for r in hourly_volume],
            "score_stats": dict(score_stats) if score_stats else {}
        }
    except Exception as e:
        return {"error": str(e)}


def create_score_gauge(score: float, title: str, color_scale: str = "RdYlGn_r") -> go.Figure:
    """Create a score gauge chart."""
    # Determine color based on score
    if score < 0.3:
        color = "#10b981"  # Green
    elif score < 0.6:
        color = "#f59e0b"  # Yellow
    elif score < 0.8:
        color = "#f97316"  # Orange
    else:
        color = "#ef4444"  # Red

    # Rich dark-mode gauge zone colors
    gauge_steps = [
        {'range': [0, 30], 'color': '#064e3b'},    # Deep green
        {'range': [30, 60], 'color': '#713f12'},    # Deep amber
        {'range': [60, 80], 'color': '#7c2d12'},    # Deep orange
        {'range': [80, 100], 'color': '#7f1d1d'}    # Deep red
    ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score * 100,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 14, 'color': _DARK_TEXT}},
        number={'suffix': "%", 'font': {'size': 24, 'color': _DARK_TEXT}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': _DARK_MUTED},
            'bar': {'color': color},
            'bgcolor': _DARK_BG,
            'borderwidth': 2,
            'bordercolor': _DARK_BORDER,
            'steps': gauge_steps,
            'threshold': {
                'line': {'color': color, 'width': 2},
                'thickness': 0.75,
                'value': score * 100
            }
        }
    ))

    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        font={'color': _DARK_TEXT},
    )

    return fig


def get_decision_badge(decision: str) -> str:
    """Get HTML badge for decision."""
    badges = {
        "ALLOW": '<span class="decision-allow">ALLOW</span>',
        "FRICTION": '<span class="decision-friction">FRICTION</span>',
        "REVIEW": '<span class="decision-review">REVIEW</span>',
        "BLOCK": '<span class="decision-block">BLOCK</span>',
    }
    return badges.get(decision, decision)


def get_severity_badge(severity: str) -> str:
    """Get HTML badge for severity."""
    badges = {
        "CRITICAL": '<span class="severity-critical">CRITICAL</span>',
        "HIGH": '<span class="severity-high">HIGH</span>',
        "MEDIUM": '<span class="severity-medium">MEDIUM</span>',
        "LOW": '<span class="severity-low">LOW</span>',
    }
    return badges.get(severity, severity)


# ============================================================================
# Transaction Presets - Telco/MSP Payment Fraud Scenarios
# ============================================================================

TRANSACTION_PRESETS = {
    "SIM Activation (Normal)": {
        "description": "Legitimate SIM activation from established subscriber",
        "payload": {
            "amount_cents": 2500,  # $25 activation fee
            "card_bin": "411111",
            "card_last_four": "1234",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_name": "Telco Mobile Prepaid",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "sim_activation",
            "subscriber_id": "subscriber_123",
            "phone_number": "15551234567",
            "imei": "353456789012345",
            "sim_iccid": "89012600001234567890",
            "account_age_days": 365,
            "is_guest": False,
            "channel": "mobile",
            "device": {
                "device_type": "mobile",
                "os": "iOS",
                "os_version": "17.0",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "192.168.1.100",
                "country_code": "US",
                "is_vpn": False,
                "is_proxy": False,
                "is_datacenter": False,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "Y",
                "cvv_result": "M",
            }
        }
    },
    "SIM Farm Attack": {
        "description": "Rapid SIM activations with same card (SIM farm setup)",
        "payload": {
            "amount_cents": 0,  # Free SIM activation
            "card_bin": "411111",
            "card_last_four": "9999",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "sim_activation",
            "subscriber_id": "subscriber_farm_001",
            "phone_number": "15559999999",
            "imei": "353456789099999",
            "account_age_days": 1,
            "is_guest": True,
            "channel": "web",
            "device": {
                "device_type": "desktop",
                "os": "Windows",
                "is_emulator": True,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "203.0.113.50",
                "country_code": "US",
                "is_vpn": True,
                "is_datacenter": True,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "N",
                "cvv_result": "N",
            }
        }
    },
    "Card Testing (Topup)": {
        "description": "Small topups to test stolen card validity",
        "payload": {
            "amount_cents": 500,  # $5 minimum topup
            "card_bin": "411111",
            "card_last_four": "8888",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "topup",
            "subscriber_id": "subscriber_test_001",
            "phone_number": "15558888888",
            "account_age_days": 1,
            "is_guest": True,
            "channel": "web",
            "device": {
                "device_type": "desktop",
                "os": "Windows",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "198.51.100.25",
                "country_code": "US",
                "is_vpn": True,
                "is_datacenter": True,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "N",
                "cvv_result": "N",
            }
        }
    },
    "Device Upgrade Fraud": {
        "description": "Subsidized device purchase from new subscriber (resale fraud)",
        "payload": {
            "amount_cents": 99900,  # $999 subsidized device
            "card_bin": "555555",
            "card_last_four": "4444",
            "card_brand": "Mastercard",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "device_upgrade",
            "subscriber_id": "subscriber_new_001",
            "phone_number": "15554444444",
            "imei": "353456789044444",
            "account_age_days": 7,
            "is_guest": False,
            "channel": "web",
            "device": {
                "device_type": "desktop",
                "os": "Linux",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "198.51.100.25",
                "country_code": "US",
                "is_vpn": False,
                "is_datacenter": False,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "Y",
                "cvv_result": "M",
            }
        }
    },
    "SIM Swap (Account Takeover)": {
        "description": "SIM swap request (potential account takeover)",
        "payload": {
            "amount_cents": 0,  # Free SIM swap
            "card_bin": "411111",
            "card_last_four": "5678",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "sim_swap",
            "subscriber_id": "subscriber_existing_001",
            "phone_number": "15555678901",
            "sim_iccid": "89012600009999999999",
            "account_age_days": 180,
            "is_guest": False,
            "channel": "call_center",
            "device": {
                "device_type": "mobile",
                "os": "Android",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "41.190.2.100",
                "country_code": "NG",  # Different country
                "is_vpn": False,
                "is_datacenter": False,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "N",
                "cvv_result": "M",
            }
        }
    },
    "Equipment Fraud (Broadband)": {
        "description": "CPE/modem purchase for resale fraud",
        "payload": {
            "amount_cents": 19900,  # $199 equipment
            "card_bin": "378282",
            "card_last_four": "0005",
            "card_brand": "Amex",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "broadband_fiber_001",
            "service_type": "broadband",
            "service_region": "US",
            "event_subtype": "equipment_purchase",
            "subscriber_id": "subscriber_equip_001",
            "modem_mac": "00:1A:2B:3C:4D:5E",
            "cpe_serial": "CPE-001234",
            "service_address_hash": "addr_hash_12345",
            "account_age_days": 3,
            "is_guest": False,
            "channel": "web",
            "device": {
                "device_type": "desktop",
                "os": "Windows",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "185.220.101.50",
                "country_code": "US",
                "is_vpn": True,
                "is_datacenter": True,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "Y",
                "cvv_result": "M",
            }
        }
    },
    "International Enable (IRSF Risk)": {
        "description": "International roaming enable (IRSF fraud setup)",
        "payload": {
            "amount_cents": 5000,  # $50 setup fee
            "card_bin": "411111",
            "card_last_four": "7777",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "service_region": "US",
            "event_subtype": "international_enable",
            "subscriber_id": "subscriber_intl_001",
            "phone_number": "15557777777",
            "account_age_days": 14,
            "is_guest": False,
            "channel": "web",
            "device": {
                "device_type": "mobile",
                "os": "Android",
                "os_version": "12.0",
                "is_emulator": False,
                "is_rooted": True,
            },
            "geo": {
                "ip_address": "185.220.101.50",
                "country_code": "DE",
                "is_vpn": True,
                "is_datacenter": True,
                "is_tor": True,
            },
            "verification": {
                "avs_result": "N",
                "cvv_result": "N",
            }
        }
    },
    "Broadband Activation (Normal)": {
        "description": "Legitimate broadband service activation",
        "payload": {
            "amount_cents": 9900,  # $99 activation fee
            "card_bin": "411111",
            "card_last_four": "2222",
            "card_brand": "Visa",
            "card_type": "debit",
            "card_country": "US",
            "service_id": "broadband_fiber_001",
            "service_name": "Telco Broadband Fiber",
            "service_type": "broadband",
            "service_region": "US",
            "event_subtype": "service_activation",
            "subscriber_id": "subscriber_bb_001",
            "modem_mac": "00:1A:2B:AA:BB:CC",
            "cpe_serial": "CPE-002222",
            "service_address_hash": "addr_hash_22222",
            "account_age_days": 60,
            "is_guest": False,
            "channel": "web",
            "device": {
                "device_type": "desktop",
                "os": "macOS",
                "is_emulator": False,
                "is_rooted": False,
            },
            "geo": {
                "ip_address": "172.16.0.100",
                "country_code": "US",
                "is_vpn": False,
                "is_datacenter": False,
                "is_tor": False,
            },
            "verification": {
                "avs_result": "Y",
                "cvv_result": "M",
            }
        }
    },
}


# ============================================================================
# Main Dashboard
# ============================================================================

def main():
    # Header - hiring-manager-friendly value prop
    st.markdown("""
    <div class="dashboard-header">
        <h1>Telco/MSP Payment Fraud Detection Platform</h1>
        <p class="subtitle">
            Real-time payment fraud detection engine for Telecom and Managed Service Providers.
            Every transaction is scored in under 200ms using a combination of rule-based detectors
            and ML models with Champion/Challenger A/B testing.
        </p>
        <div class="tech-pills">
            <span class="tech-pill">FastAPI</span>
            <span class="tech-pill">PostgreSQL</span>
            <span class="tech-pill">Redis</span>
            <span class="tech-pill">scikit-learn + XGBoost</span>
            <span class="tech-pill">Prometheus</span>
            <span class="tech-pill">Hot-Reload Policy</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick Guide button + popup
    if "show_guide" not in st.session_state:
        st.session_state.show_guide = False

    guide_cols = st.columns([1, 6])
    with guide_cols[0]:
        if st.button("Quick Guide", type="secondary", use_container_width=True):
            st.session_state.show_guide = not st.session_state.show_guide

    if st.session_state.show_guide:
        st.html("""
        <style>
            .qg-box {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem 2rem;
                margin-bottom: 1rem;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                color: #e2e8f0;
            }
            .qg-box h3 {
                margin: 0 0 0.25rem 0;
                font-size: 1.15rem;
                color: #f1f5f9;
            }
            .qg-subtitle {
                color: #94a3b8;
                font-size: 0.9rem;
                margin: 0 0 1.25rem 0;
            }
            .qg-activity {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 1rem 1.25rem;
                margin-bottom: 0.75rem;
                transition: border-color 0.2s;
            }
            .qg-activity:hover { border-color: #3b82f6; }
            .qg-activity h4 {
                margin: 0 0 0.5rem 0;
                font-size: 0.95rem;
                color: #f1f5f9;
            }
            .qg-num {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                background: #3b82f6;
                color: white;
                border-radius: 50%;
                font-size: 0.75rem;
                font-weight: 700;
                margin-right: 0.5rem;
            }
            .qg-step {
                padding: 0.2rem 0 0.2rem 2.25rem;
                font-size: 0.85rem;
                color: #cbd5e1;
            }
            .qg-marker {
                color: #64748b;
                margin-right: 0.4rem;
                font-weight: 600;
            }
        </style>
        <div class="qg-box">
            <h3>Quick Guide</h3>
            <p class="qg-subtitle">Three things you can do on this dashboard right now:</p>

            <div class="qg-activity">
                <h4><span class="qg-num">1</span> Run a Fraud Simulation</h4>
                <div class="qg-step"><span class="qg-marker">a.</span> Go to the <b>Simulate</b> tab</div>
                <div class="qg-step"><span class="qg-marker">b.</span> Pick a preset scenario (e.g. "SIM Swap Fraud" or "Normal Activation")</div>
                <div class="qg-step"><span class="qg-marker">c.</span> Click <b>Submit Transaction</b> and watch the real-time decision</div>
                <div class="qg-step"><span class="qg-marker">d.</span> Review the risk scores, triggered rules, and latency metrics</div>
            </div>

            <div class="qg-activity">
                <h4><span class="qg-num">2</span> Review Detection Analytics</h4>
                <div class="qg-step"><span class="qg-marker">a.</span> Go to the <b>Overview</b> tab after running a few simulations</div>
                <div class="qg-step"><span class="qg-marker">b.</span> Check decision distribution (Allow vs Block vs Friction vs Review)</div>
                <div class="qg-step"><span class="qg-marker">c.</span> Monitor latency vs the 200ms SLO target</div>
            </div>

            <div class="qg-activity">
                <h4><span class="qg-num">3</span> Inspect the Policy Engine</h4>
                <div class="qg-step"><span class="qg-marker">a.</span> Go to the <b>Policy</b> tab</div>
                <div class="qg-step"><span class="qg-marker">b.</span> View score thresholds that control Allow/Friction/Review/Block decisions</div>
                <div class="qg-step"><span class="qg-marker">c.</span> Explore active rules, blocklists, and version history with rollback</div>
            </div>
        </div>
        """)

    # Sidebar - System Status (compact, professional)
    with st.sidebar:
        st.markdown("### System Status")

        health = get_api_health()

        # Overall status - prominent indicator
        status = health.get("status", "down")
        if status == "healthy":
            st.success("System Healthy")
        elif status == "degraded":
            st.warning("System Degraded")
        else:
            st.error("System Down")

        # Component status - compact row
        components = health.get("components", {})
        component_items = [
            ("Redis", components.get("redis")),
            ("Postgres", components.get("postgres")),
            ("Policy", components.get("policy")),
        ]
        component_html = " &nbsp; ".join(
            f'<span style="color:{"#10b981" if ok else "#ef4444"};">{"&#10003;" if ok else "&#10007;"}</span> {name}'
            for name, ok in component_items
        )
        st.markdown(f'<div style="font-size:0.85rem;">{component_html}</div>', unsafe_allow_html=True)

        # Policy version
        policy = get_policy_version()
        st.caption(f"Policy: v{policy.get('version', 'N/A')}")

        st.divider()

        # ML Model Status - compact
        st.markdown("### ML Scoring")
        registry = get_model_registry()
        if registry:
            champion = registry.get("champion")
            challenger = registry.get("challenger")
            if champion:
                st.markdown(f"**Champion:** `{champion.get('name', 'N/A')}` (AUC {champion.get('auc', 0):.4f})")
            if challenger:
                st.markdown(f"**Challenger:** `{challenger.get('name', 'N/A')}` (AUC {challenger.get('auc', 0):.4f})")
        else:
            st.caption("No models registered")

        st.divider()

        # Architecture Highlights
        st.markdown("### Architecture")
        st.markdown("""
        <div style="font-size: 0.82rem; line-height: 1.7;">
        <div><span style="color: #3b82f6;">&#9632;</span> <b>&lt;200ms</b> P99 latency target</div>
        <div><span style="color: #10b981;">&#9632;</span> <b>Rules + ML</b> A/B testing</div>
        <div><span style="color: #f59e0b;">&#9632;</span> <b>Redis + Postgres</b> + Prometheus</div>
        <div><span style="color: #8b5cf6;">&#9632;</span> <b>Encrypted</b> evidence vault</div>
        <div><span style="color: #ef4444;">&#9632;</span> <b>Hot-reload</b> policy engine</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Quick stats from last decision
        if "last_decision" in st.session_state:
            st.markdown("### Last Decision")
            last = st.session_state.last_decision
            st.markdown(get_decision_badge(last.get("decision", "N/A")), unsafe_allow_html=True)
            st.metric("Latency", f"{last.get('processing_time_ms', 0):.1f}ms")

    # Main content tabs - reordered for hiring manager flow
    tabs = st.tabs([
        "Overview",
        "Simulate",
        "Decision History",
        "ML Performance",
        "Policy",
    ])

    # ==========================================================================
    # Tab 2: Transaction Simulator
    # ==========================================================================
    with tabs[1]:
        st.markdown("""
        <div class="tab-intro">
            <b>Simulate fraud transactions</b> against the live detection engine.
            Pick a preset scenario, submit it, and see the real-time decision with risk scores and triggered rules.
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Submit Transaction")

            # Preset selector
            preset_name = st.selectbox(
                "Select Preset",
                options=list(TRANSACTION_PRESETS.keys()),
                help="Choose a preset transaction scenario"
            )

            preset = TRANSACTION_PRESETS[preset_name]
            st.info(preset["description"])

            # Transaction details
            st.markdown("**Transaction Details**")

            preset_amount = preset["payload"]["amount_cents"] / 100
            amount = st.number_input(
                "Amount ($)",
                min_value=0.00,
                value=preset_amount,
                step=1.0,
                help="$0.00 is valid for free activations/swaps"
            )

            service_id = st.text_input(
                "Service ID",
                value=preset["payload"].get("service_id", f"service_{uuid4().hex[:8]}")
            )

            # Advanced options
            with st.expander("Advanced Options"):
                card_token = st.text_input(
                    "Card Token",
                    value=f"card_{uuid4().hex[:12]}"
                )

                user_id = st.text_input(
                    "User ID",
                    value=f"user_{uuid4().hex[:8]}"
                )

                is_emulator = st.checkbox(
                    "Emulator",
                    value=preset["payload"].get("device", {}).get("is_emulator", False)
                )

                is_tor = st.checkbox(
                    "Tor Exit Node",
                    value=preset["payload"].get("geo", {}).get("is_tor", False)
                )

                is_datacenter = st.checkbox(
                    "Datacenter IP",
                    value=preset["payload"].get("geo", {}).get("is_datacenter", False)
                )

            # Submit button
            if st.button("Submit Transaction", type="primary", use_container_width=True):
                # Build payload
                payload = preset["payload"].copy()
                payload["transaction_id"] = f"txn_{uuid4().hex[:16]}"
                payload["idempotency_key"] = f"idem_{uuid4().hex[:16]}"
                payload["amount_cents"] = int(amount * 100)
                payload["service_id"] = service_id
                payload["card_token"] = card_token
                payload["user_id"] = user_id

                # Update device/geo from checkboxes
                if "device" not in payload:
                    payload["device"] = {}
                payload["device"]["device_id"] = f"dev_{uuid4().hex[:12]}"
                payload["device"]["is_emulator"] = is_emulator

                if "geo" not in payload:
                    payload["geo"] = {}
                payload["geo"]["is_tor"] = is_tor
                payload["geo"]["is_datacenter"] = is_datacenter

                # Submit
                with st.spinner("Processing..."):
                    result = submit_transaction(payload)

                if "error" not in result:
                    st.session_state.last_decision = result
                    st.session_state.last_payload = payload
                    st.success("Transaction processed!")
                else:
                    st.error(f"Error: {result['error']}")

        with col2:
            st.subheader("Decision Result")

            if "last_decision" in st.session_state:
                result = st.session_state.last_decision

                # Decision badge
                decision = result.get("decision", "N/A")
                st.markdown(f"### {get_decision_badge(decision)}", unsafe_allow_html=True)

                # Executive summary: plain-English explanation
                risk_score = result.get("scores", {}).get("risk_score", 0)
                reasons = result.get("reasons", [])
                processing_ms = result.get("processing_time_ms", 0)
                slo_met = processing_ms < 200

                reason_summary = ""
                if reasons:
                    top_reasons = [r.get("code", "UNKNOWN") for r in reasons[:3]]
                    reason_summary = f" Triggered by: <b>{', '.join(top_reasons)}</b>."
                elif decision == "ALLOW":
                    reason_summary = " No risk factors detected."

                slo_tag = f'<span style="color:#10b981;">within SLO</span>' if slo_met else f'<span style="color:#ef4444;">SLO breach</span>'

                st.markdown(f"""
                <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:1rem 1.25rem;margin-bottom:1rem;">
                    <span style="font-size:0.95rem;color:#e2e8f0;">
                        <b>Decision: {decision}</b> with risk score <b>{risk_score*100:.0f}%</b> in <b>{processing_ms:.1f}ms</b> ({slo_tag}).{reason_summary}
                    </span>
                </div>
                """, unsafe_allow_html=True)

                # Metrics row
                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.metric("Transaction ID", result.get("transaction_id", "N/A")[:16] + "...")
                with metric_cols[1]:
                    lat_delta = processing_ms - 200
                    st.metric("Processing Time", f"{processing_ms:.2f}ms",
                              delta=f"{lat_delta:+.0f}ms vs SLO" if processing_ms > 0 else None,
                              delta_color="inverse")
                with metric_cols[2]:
                    st.metric("Policy Version", result.get("policy_version", "N/A"))
                with metric_cols[3]:
                    st.metric("Cached", "Yes" if result.get("is_cached") else "No")

                st.divider()

                # Score gauges
                st.markdown("#### Risk Scores")
                scores = result.get("scores", {})

                has_ml = scores.get("ml_score") is not None
                n_gauges = 5 if has_ml else 4
                gauge_cols = st.columns(n_gauges)
                with gauge_cols[0]:
                    fig = create_score_gauge(scores.get("risk_score", 0), "Overall Risk")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[1]:
                    fig = create_score_gauge(scores.get("criminal_score", 0), "Criminal")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[2]:
                    fig = create_score_gauge(scores.get("friendly_fraud_score", 0), "Friendly Fraud")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[3]:
                    fig = create_score_gauge(scores.get("bot_score", 0), "Bot Score")
                    st.plotly_chart(fig, use_container_width=True)
                if has_ml:
                    with gauge_cols[4]:
                        fig = create_score_gauge(scores.get("ml_score", 0), "ML Model")
                        st.plotly_chart(fig, use_container_width=True)

                # ML Model info bar
                if has_ml:
                    ml_cols = st.columns(3)
                    with ml_cols[0]:
                        variant = scores.get("model_variant", "unknown")
                        variant_colors = {"champion": "#10b981", "challenger": "#f59e0b", "holdout": "#6b7280"}
                        color = variant_colors.get(variant, "#6b7280")
                        st.markdown(f'<span style="background-color:{color};color:white;padding:4px 12px;border-radius:9999px;font-weight:600;font-size:0.85rem;">{variant.upper()}</span>', unsafe_allow_html=True)
                    with ml_cols[1]:
                        st.markdown(f"**Model:** `{scores.get('model_version', 'N/A')}`")
                    with ml_cols[2]:
                        st.markdown(f"**ML Score:** {scores.get('ml_score', 0)*100:.1f}%")

                # Detailed scores
                with st.expander("Detailed Score Breakdown"):
                    score_cols = st.columns(5 if has_ml else 4)
                    with score_cols[0]:
                        st.metric("Card Testing", f"{scores.get('card_testing_score', 0)*100:.1f}%")
                    with score_cols[1]:
                        st.metric("Velocity", f"{scores.get('velocity_score', 0)*100:.1f}%")
                    with score_cols[2]:
                        st.metric("Geo Anomaly", f"{scores.get('geo_score', 0)*100:.1f}%")
                    with score_cols[3]:
                        st.metric("Confidence", f"{scores.get('confidence', 0)*100:.1f}%")
                    if has_ml:
                        with score_cols[4]:
                            st.metric("ML Score", f"{scores.get('ml_score', 0)*100:.1f}%")

                st.divider()

                # Triggered reasons
                st.markdown("#### Triggered Reasons")
                reasons = result.get("reasons", [])

                if reasons:
                    for reason in reasons:
                        severity = reason.get("severity", "LOW")
                        code = reason.get("code", "UNKNOWN")
                        description = reason.get("description", "No description")

                        st.markdown(f"""
                        <div class="reason-card">
                            {get_severity_badge(severity)} <strong>{code}</strong><br/>
                            <span style="color: #94a3b8;">{description}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("No risk factors detected")

                # Friction/Review info
                if result.get("friction_type"):
                    st.warning(f"**Friction Required:** {result['friction_type']} - {result.get('friction_message', '')}")

                if result.get("review_priority"):
                    st.info(f"**Review Priority:** {result['review_priority']} - {result.get('review_notes', '')}")

                # Raw JSON
                with st.expander("Raw API Response"):
                    st.json(result)
            else:
                st.markdown("""
                <div class="empty-state">
                    <div class="empty-state-icon">&#127919;</div>
                    <div class="empty-state-title">No Results Yet</div>
                    <div class="empty-state-desc">
                        Select a preset scenario on the left and click <b>Submit Transaction</b>
                        to see the fraud detection engine in action.
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # ==========================================================================
    # Tab 1: Overview (Analytics Dashboard)
    # ==========================================================================
    with tabs[0]:
        st.markdown("""
        <div class="tab-intro">
            <b>System-wide analytics</b> showing transaction volumes, decision distribution,
            risk score trends, and latency performance against the 200ms SLO target.
        </div>
        """, unsafe_allow_html=True)

        # Time-window selector
        analytics_window_options = {
            "Last 1 hour": 1,
            "Last 6 hours": 6,
            "Last 24 hours": 24,
            "Last 7 days": 168,
            "All time": None,
        }
        selected_analytics_window = st.selectbox(
            "Analytics Window",
            options=list(analytics_window_options.keys()),
            index=4,  # Default to "All time"
            key="analytics_window",
        )
        analytics_window_hours = analytics_window_options[selected_analytics_window]

        # Get analytics data
        try:
            analytics = asyncio.run(get_analytics_data(window_hours=analytics_window_hours))
        except Exception as e:
            analytics = {"error": str(e)}

        if "error" in analytics:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">&#128202;</div>
                <div class="empty-state-title">No Analytics Data</div>
                <div class="empty-state-desc">
                    Go to the <b>Simulate</b> tab and submit a few transactions to populate this dashboard with analytics data.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Key metrics
            stats = analytics.get("score_stats", {})
            window_label = selected_analytics_window.replace("Last ", "")

            _SLO_TARGET_MS = 200  # P99 latency SLO target

            metric_cols = st.columns(5)
            with metric_cols[0]:
                st.metric(
                    f"Total Transactions ({window_label})",
                    f"{stats.get('total_count', 0):,}",
                    help="Total fraud decisions processed in this time window"
                )
            with metric_cols[1]:
                avg_risk = (stats.get('avg_risk', 0) or 0) * 100
                st.metric(
                    "Avg Risk Score",
                    f"{avg_risk:.1f}%",
                    help="Mean risk score across all transactions. Lower is better."
                )
            with metric_cols[2]:
                p95_risk = (stats.get('p95_risk', 0) or 0) * 100
                st.metric(
                    "P95 Risk Score",
                    f"{p95_risk:.1f}%",
                    help="95th percentile risk score -- tail risk indicator"
                )
            with metric_cols[3]:
                avg_lat = stats.get('avg_latency', 0) or 0
                lat_delta = avg_lat - _SLO_TARGET_MS
                st.metric(
                    "Avg Latency",
                    f"{avg_lat:.1f}ms",
                    delta=f"{lat_delta:+.0f}ms vs SLO" if avg_lat > 0 else None,
                    delta_color="inverse",
                    help=f"Average end-to-end decision latency. SLO target: <{_SLO_TARGET_MS}ms"
                )
            with metric_cols[4]:
                p99_lat = stats.get('p99_latency', 0) or 0
                p99_delta = p99_lat - _SLO_TARGET_MS
                st.metric(
                    "P99 Latency",
                    f"{p99_lat:.1f}ms",
                    delta=f"{p99_delta:+.0f}ms vs SLO" if p99_lat > 0 else None,
                    delta_color="inverse",
                    help=f"99th percentile latency. SLO target: <{_SLO_TARGET_MS}ms P99"
                )

            st.divider()

            # Charts row
            chart_cols = st.columns(2)

            with chart_cols[0]:
                st.markdown("#### Decision Distribution")
                decision_data = analytics.get("decision_distribution", [])
                if decision_data:
                    df = pd.DataFrame(decision_data)
                    colors = {
                        "ALLOW": "#10b981",
                        "FRICTION": "#f59e0b",
                        "REVIEW": "#f97316",
                        "BLOCK": "#ef4444"
                    }
                    fig = px.pie(
                        df,
                        values="count",
                        names="decision",
                        color="decision",
                        color_discrete_map=colors,
                        hole=0.4
                    )
                    fig.update_layout(
                        margin=dict(l=20, r=20, t=20, b=20),
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                        paper_bgcolor='rgba(0,0,0,0)',
                        font={'color': _DARK_TEXT},
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No decision data available")

            with chart_cols[1]:
                st.markdown("#### Hourly Transaction Volume")
                hourly_data = analytics.get("hourly_volume", [])
                if hourly_data:
                    df = pd.DataFrame(hourly_data)
                    fig = px.bar(
                        df,
                        x="hour",
                        y="count",
                        color_discrete_sequence=["#3b82f6"]
                    )
                    fig.update_layout(
                        margin=dict(l=20, r=20, t=20, b=20),
                        xaxis_title="Hour",
                        yaxis_title="Transactions",
                        showlegend=False,
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font={'color': _DARK_TEXT},
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hourly data available")

            # Latency chart
            st.markdown("#### Latency vs SLO Target (200ms)")
            if hourly_data:
                df = pd.DataFrame(hourly_data)
                fig = px.line(
                    df,
                    x="hour",
                    y="avg_latency",
                    markers=True,
                    color_discrete_sequence=["#8b5cf6"]
                )
                # SLO compliance zone shading
                fig.add_hrect(
                    y0=0, y1=200,
                    fillcolor="#10b981", opacity=0.06,
                    line_width=0,
                    annotation_text="SLO Compliant", annotation_position="top left",
                    annotation_font_color="#10b981", annotation_font_size=11,
                )
                fig.add_hrect(
                    y0=200, y1=max(float(df["avg_latency"].max()) * 1.2, 400),
                    fillcolor="#ef4444", opacity=0.06,
                    line_width=0,
                    annotation_text="SLO Breach", annotation_position="top left",
                    annotation_font_color="#ef4444", annotation_font_size=11,
                )
                fig.add_hline(
                    y=200,
                    line_dash="dash",
                    line_color="#ef4444",
                    annotation_text="P99 Target: 200ms"
                )
                fig.update_layout(
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis_title="Hour",
                    yaxis_title="Avg Latency (ms)",
                    showlegend=False,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': _DARK_TEXT},
                )
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================================================
    # Tab 3: Decision History
    # ==========================================================================
    with tabs[2]:
        st.markdown("""
        <div class="tab-intro">
            <b>Full decision audit trail.</b> Every transaction processed by the engine is logged here
            with its decision, risk scores, ML variant, and processing latency.
        </div>
        """, unsafe_allow_html=True)

        # Filters
        filter_cols = st.columns(4)
        with filter_cols[0]:
            limit = st.selectbox("Show", [25, 50, 100, 250], index=1)
        with filter_cols[1]:
            decision_filter = st.multiselect(
                "Decision",
                ["ALLOW", "FRICTION", "REVIEW", "BLOCK"],
                default=[]
            )

        # Refresh button
        if st.button("🔄 Refresh", key="refresh_history"):
            st.rerun()

        # Get history
        try:
            df = asyncio.run(get_decision_history(limit))
        except Exception as e:
            df = pd.DataFrame()
            st.error(f"Error loading history: {e}")

        if not df.empty:
            # Apply filters
            if decision_filter:
                df = df[df["decision"].isin(decision_filter)]

            # Format columns
            df["amount"] = df["amount_cents"].apply(lambda x: f"${x/100:,.2f}")
            df["risk"] = df["risk_score"].apply(lambda x: f"{x*100:.1f}%" if x else "N/A")
            df["ml"] = df["ml_score"].apply(lambda x: f"{x*100:.1f}%" if x and x > 0 else "-")
            df["variant"] = df["model_variant"].apply(lambda x: x if x else "rules")
            df["latency"] = df["processing_time_ms"].apply(lambda x: f"{x:.1f}ms" if x else "N/A")
            df["time"] = pd.to_datetime(df["captured_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

            # Decision color HTML for visual emphasis
            _DECISION_COLORS = {
                "ALLOW": "#10b981",
                "FRICTION": "#f59e0b",
                "REVIEW": "#f97316",
                "BLOCK": "#ef4444",
            }
            df["decision_display"] = df["decision"].apply(
                lambda d: f'<span style="color:{_DECISION_COLORS.get(d, "#94a3b8")};font-weight:700;">{d}</span>'
            )

            # Reordered: Decision first, then amount/risk, transaction ID last
            st.markdown(
                df[["decision_display", "amount", "risk", "ml", "variant", "latency", "time", "transaction_id"]]
                .rename(columns={
                    "decision_display": "Decision",
                    "amount": "Amount",
                    "risk": "Risk",
                    "ml": "ML",
                    "variant": "Variant",
                    "latency": "Latency",
                    "time": "Time",
                    "transaction_id": "Transaction ID",
                })
                .to_html(escape=False, index=False, classes="styled-table"),
                unsafe_allow_html=True,
            )

            # Summary stats
            st.divider()
            summary_cols = st.columns(4)
            with summary_cols[0]:
                approval_rate = len(df[df["decision"] == "ALLOW"]) / len(df) * 100 if len(df) > 0 else 0
                st.metric("Approval Rate", f"{approval_rate:.1f}%")
            with summary_cols[1]:
                block_rate = len(df[df["decision"] == "BLOCK"]) / len(df) * 100 if len(df) > 0 else 0
                st.metric("Block Rate", f"{block_rate:.1f}%")
            with summary_cols[2]:
                avg_risk = df["risk_score"].mean() * 100 if "risk_score" in df else 0
                st.metric("Avg Risk Score", f"{avg_risk:.1f}%")
            with summary_cols[3]:
                avg_latency = df["processing_time_ms"].mean() if "processing_time_ms" in df else 0
                st.metric("Avg Latency", f"{avg_latency:.1f}ms")
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">&#128220;</div>
                <div class="empty-state-title">No Transaction History</div>
                <div class="empty-state-desc">
                    Submit transactions via the <b>Simulate</b> tab to see the full decision audit trail here.
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ==========================================================================
    # Tab 4: ML Performance
    # ==========================================================================
    with tabs[3]:
        st.markdown("""
        <div class="tab-intro">
            <b>ML model performance and A/B testing.</b> Compare Champion vs Challenger models,
            view traffic routing distribution, and analyze ML score distributions across live traffic.
        </div>
        """, unsafe_allow_html=True)
        st.subheader("ML Model Performance")

        # Model registry info
        registry = get_model_registry()
        if registry:
            st.markdown("#### Model Registry")
            reg_cols = st.columns(2)

            champion = registry.get("champion")
            challenger = registry.get("challenger")

            with reg_cols[0]:
                st.markdown("##### Champion Model")
                if champion:
                    st.markdown(f"**Name:** `{champion.get('name', 'N/A')}`")
                    st.markdown(f"**Framework:** {champion.get('framework', 'N/A')}")
                    st.markdown(f"**AUC:** {champion.get('auc', 0):.4f}")
                    st.markdown(f"**Features:** {len(champion.get('feature_columns', []))}")
                    trained = champion.get("trained_at", "")[:19].replace("T", " ") if champion.get("trained_at") else "N/A"
                    st.markdown(f"**Trained:** {trained}")
                    training_window = champion.get("training_window", {})
                    if training_window:
                        start = training_window.get("start", "")[:10]
                        end = training_window.get("end", "")[:10]
                        st.markdown(f"**Window:** {start} to {end}")
                else:
                    st.info("No champion model registered")

            with reg_cols[1]:
                st.markdown("##### Challenger Model")
                if challenger:
                    st.markdown(f"**Name:** `{challenger.get('name', 'N/A')}`")
                    st.markdown(f"**Framework:** {challenger.get('framework', 'N/A')}")
                    st.markdown(f"**AUC:** {challenger.get('auc', 0):.4f}")
                    st.markdown(f"**Features:** {len(challenger.get('feature_columns', []))}")
                    trained = challenger.get("trained_at", "")[:19].replace("T", " ") if challenger.get("trained_at") else "N/A"
                    st.markdown(f"**Trained:** {trained}")
                    training_window = challenger.get("training_window", {})
                    if training_window:
                        start = training_window.get("start", "")[:10]
                        end = training_window.get("end", "")[:10]
                        st.markdown(f"**Window:** {start} to {end}")
                else:
                    st.info("No challenger model registered")

            # AUC comparison bar chart with winner indicator
            if champion and challenger:
                champ_auc = champion.get("auc", 0)
                chall_auc = challenger.get("auc", 0)
                auc_delta = chall_auc - champ_auc
                if auc_delta > 0:
                    winner_text = f'<span style="color:#f59e0b;font-weight:600;">Challenger leads by +{auc_delta:.4f}</span>'
                elif auc_delta < 0:
                    winner_text = f'<span style="color:#10b981;font-weight:600;">Champion leads by +{abs(auc_delta):.4f}</span>'
                else:
                    winner_text = '<span style="color:#94a3b8;">Models tied</span>'
                st.markdown(f"#### AUC Comparison &nbsp;&nbsp; {winner_text}", unsafe_allow_html=True)
                auc_data = pd.DataFrame({
                    "Model": [f"Champion ({champion.get('framework', '?')})", f"Challenger ({challenger.get('framework', '?')})"],
                    "AUC": [champion.get("auc", 0), challenger.get("auc", 0)]
                })
                fig = px.bar(
                    auc_data, x="Model", y="AUC",
                    color="Model",
                    color_discrete_sequence=["#10b981", "#f59e0b"],
                    text="AUC"
                )
                fig.update_traces(texttemplate='%{text:.4f}', textposition='outside')
                fig.update_layout(
                    yaxis_range=[0.8, 1.0],
                    showlegend=False,
                    height=300,
                    margin=dict(l=20, r=20, t=20, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': _DARK_TEXT},
                )
                fig.add_hline(y=0.85, line_dash="dash", line_color="red", annotation_text="Min AUC: 0.85")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No model registry found. Ensure models/registry.json exists.")

        st.divider()

        # Time window selector
        window_options = {
            "Last 1 hour": 1,
            "Last 6 hours": 6,
            "Last 24 hours": 24,
            "Last 7 days": 168,
            "All time": None,
        }
        selected_window = st.selectbox(
            "Analytics Window",
            options=list(window_options.keys()),
            index=4,  # Default to "All time"
            key="ml_window",
        )
        window_hours = window_options[selected_window]

        # ML analytics from DB
        st.markdown(f"#### Live Traffic Analytics ({selected_window.lower()})")
        try:
            ml_analytics = asyncio.run(get_ml_analytics(window_hours=window_hours))
        except Exception as e:
            ml_analytics = {"error": str(e)}

        if "error" in ml_analytics:
            st.warning(f"Could not load ML analytics: {ml_analytics.get('error')}")
            st.info("Submit transactions with ML enabled to generate analytics data.")
        else:
            # ML summary metrics row
            summary = ml_analytics.get("summary", {})
            total = summary.get("total", 0)
            ml_scored = summary.get("ml_scored", 0)
            champion_avg = summary.get("champion_avg")
            challenger_avg = summary.get("challenger_avg")

            m_cols = st.columns(3)
            with m_cols[0]:
                coverage = (ml_scored / total * 100) if total > 0 else 0
                st.metric("ML Coverage", f"{coverage:.1f}%", help="% of transactions scored by ML model")
            with m_cols[1]:
                st.metric("Champion Avg Score", f"{champion_avg:.3f}" if champion_avg is not None else "N/A")
            with m_cols[2]:
                st.metric("Challenger Avg Score", f"{challenger_avg:.3f}" if challenger_avg is not None else "N/A")

            st.markdown("")

            # Variant distribution
            variant_data = ml_analytics.get("variant_distribution", [])
            if variant_data:
                st.markdown("##### Traffic Routing Distribution")
                vdf = pd.DataFrame(variant_data)

                v_cols = st.columns(2)
                with v_cols[0]:
                    variant_colors = {
                        "champion": "#10b981",
                        "challenger": "#f59e0b",
                        "holdout": "#6b7280",
                        "rules-only": "#3b82f6"
                    }
                    fig = px.pie(
                        vdf, values="count", names="variant",
                        color="variant",
                        color_discrete_map=variant_colors,
                        hole=0.4
                    )
                    fig.update_layout(
                        height=300,
                        margin=dict(l=20, r=20, t=20, b=20),
                        paper_bgcolor='rgba(0,0,0,0)',
                        font={'color': _DARK_TEXT},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with v_cols[1]:
                    # Summary metrics table
                    for row in variant_data:
                        variant = row.get("variant", "unknown")
                        count = row.get("count", 0)
                        avg_ml = row.get("avg_ml_score")
                        avg_risk = row.get("avg_risk_score")
                        ml_str = f"{avg_ml*100:.1f}%" if avg_ml else "-"
                        risk_str = f"{avg_risk*100:.1f}%" if avg_risk else "-"
                        st.markdown(f"**{variant}**: {count:,} txns | ML avg: {ml_str} | Risk avg: {risk_str}")

            # ML score distribution histogram
            ml_scores_list = ml_analytics.get("ml_scores", [])
            if ml_scores_list:
                st.markdown("##### ML Score Distribution")
                score_df = pd.DataFrame({"ml_score": ml_scores_list})
                fig = px.histogram(
                    score_df, x="ml_score", nbins=50,
                    color_discrete_sequence=["#8b5cf6"],
                    labels={"ml_score": "ML Score"}
                )
                fig.update_layout(
                    height=300,
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis_title="ML Score",
                    yaxis_title="Count",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': _DARK_TEXT},
                )
                st.plotly_chart(fig, use_container_width=True)

            # ML Score vs Rules Score scatter plot
            ml_vs_rules = ml_analytics.get("ml_vs_rules", [])
            if ml_vs_rules:
                st.markdown("##### ML Score vs Rules Score")
                st.caption("Points above the diagonal = ML flags higher risk than rules alone")
                scatter_df = pd.DataFrame(ml_vs_rules)
                fig = px.scatter(
                    scatter_df, x="criminal_score", y="ml_score",
                    color_discrete_sequence=["#8b5cf6"],
                    labels={"criminal_score": "Rule-Based Criminal Score", "ml_score": "ML Score"},
                    opacity=0.4,
                )
                # Add diagonal reference line
                fig.add_shape(
                    type="line", x0=0, y0=0, x1=1, y1=1,
                    line=dict(color="#6b7280", width=1, dash="dash"),
                )
                fig.update_layout(
                    height=400,
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis=dict(range=[0, 1]),
                    yaxis=dict(range=[0, 1]),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': _DARK_TEXT},
                )
                st.plotly_chart(fig, use_container_width=True)

            # Decision distribution by variant
            decision_variant_data = ml_analytics.get("decision_by_variant", [])
            if decision_variant_data:
                st.markdown("##### Decisions by Model Variant")
                dvdf = pd.DataFrame(decision_variant_data)
                decision_colors = {
                    "ALLOW": "#10b981",
                    "FRICTION": "#f59e0b",
                    "REVIEW": "#f97316",
                    "BLOCK": "#ef4444"
                }
                fig = px.bar(
                    dvdf, x="variant", y="count", color="decision",
                    color_discrete_map=decision_colors,
                    barmode="group",
                    labels={"variant": "Model Variant", "count": "Transactions"}
                )
                fig.update_layout(
                    height=350,
                    margin=dict(l=20, r=20, t=20, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font={'color': _DARK_TEXT},
                    legend=dict(orientation="h", yanchor="bottom", y=-0.25),
                )
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================================================
    # Tab 5: Policy (merged Inspector + Settings)
    # ==========================================================================
    with tabs[4]:
        st.markdown("""
        <div class="tab-intro">
            <b>Policy engine configuration.</b> View and manage the fraud detection rules,
            score thresholds, blocklists/allowlists, and version history with rollback capability.
        </div>
        """, unsafe_allow_html=True)

        # Sub-tabs: Inspect (read-only) and Configure (editable)
        policy_sub_tabs = st.tabs([
            "Inspect Policy",
            "Configure",
            "Version History",
        ])

        # ==================================================================
        # Policy Inspect sub-tab (read-only view from YAML)
        # ==================================================================
        with policy_sub_tabs[0]:
            policy_path = os.path.join(os.path.dirname(__file__), "config", "policy.yaml")

            try:
                import yaml
                with open(policy_path, "r") as f:
                    policy_yaml = yaml.safe_load(f)

                # Policy version
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Version", policy_yaml.get("version", "N/A"))
                with col2:
                    st.metric("Default Action", policy_yaml.get("default_action", "ALLOW"))

                st.markdown(f"*{policy_yaml.get('description', '')}*")

                st.divider()

                # Thresholds as visual cascade bars
                st.markdown("#### Score Thresholds")
                inspect_thresholds = policy_yaml.get("thresholds", {})

                thresh_cols = st.columns(3)
                for i, (name, thresh) in enumerate(inspect_thresholds.items()):
                    with thresh_cols[i % 3]:
                        st.markdown(f"**{name.title()} Score**")
                        friction_pct = thresh.get('friction_threshold', 0) * 100
                        review_pct = thresh.get('review_threshold', 0) * 100
                        block_pct = thresh.get('block_threshold', 0) * 100

                        st.markdown(f"""
                        <div style="background:#0f172a;border-radius:6px;overflow:hidden;height:28px;position:relative;margin:0.5rem 0;">
                            <div style="position:absolute;left:0;top:0;height:100%;width:{friction_pct}%;background:#10b981;opacity:0.3;"></div>
                            <div style="position:absolute;left:{friction_pct}%;top:0;height:100%;width:{review_pct - friction_pct}%;background:#f59e0b;opacity:0.3;"></div>
                            <div style="position:absolute;left:{review_pct}%;top:0;height:100%;width:{block_pct - review_pct}%;background:#f97316;opacity:0.3;"></div>
                            <div style="position:absolute;left:{block_pct}%;top:0;height:100%;width:{100 - block_pct}%;background:#ef4444;opacity:0.3;"></div>
                        </div>
                        <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#94a3b8;">
                            <span style="color:#10b981;">Allow &lt;{friction_pct:.0f}%</span>
                            <span style="color:#f59e0b;">Friction {friction_pct:.0f}%</span>
                            <span style="color:#f97316;">Review {review_pct:.0f}%</span>
                            <span style="color:#ef4444;">Block {block_pct:.0f}%+</span>
                        </div>
                        """, unsafe_allow_html=True)

                st.divider()

                # Rules
                st.markdown("#### Active Rules")
                inspect_rules = policy_yaml.get("rules", [])

                for rule in inspect_rules:
                    if rule.get("enabled", True):
                        with st.expander(f"**{rule.get('name', 'Unknown')}** (Priority: {rule.get('priority', 100)})"):
                            st.markdown(f"*{rule.get('description', '')}*")
                            st.markdown(f"**Action:** `{rule.get('action', 'N/A')}`")
                            if rule.get("friction_type"):
                                st.markdown(f"**Friction Type:** `{rule['friction_type']}`")
                            if rule.get("review_priority"):
                                st.markdown(f"**Review Priority:** `{rule['review_priority']}`")
                            st.markdown("**Conditions:**")
                            st.json(rule.get("conditions", {}))

                st.divider()

                # Lists
                list_cols = st.columns(2)
                with list_cols[0]:
                    st.markdown("#### Blocklists")
                    st.markdown(f"- Cards: {len(policy_yaml.get('blocklist_cards', []))} entries")
                    st.markdown(f"- Devices: {len(policy_yaml.get('blocklist_devices', []))} entries")
                    st.markdown(f"- IPs: {len(policy_yaml.get('blocklist_ips', []))} entries")
                    st.markdown(f"- Users: {len(policy_yaml.get('blocklist_users', []))} entries")

                with list_cols[1]:
                    st.markdown("#### Allowlists")
                    st.markdown(f"- Cards: {len(policy_yaml.get('allowlist_cards', []))} entries")
                    st.markdown(f"- Users: {len(policy_yaml.get('allowlist_users', []))} entries")
                    st.markdown(f"- Services: {len(policy_yaml.get('allowlist_services', []))} entries")

                # Raw YAML
                with st.expander("Raw Policy YAML"):
                    st.code(yaml.dump(policy_yaml, default_flow_style=False), language="yaml")

            except Exception as e:
                st.error(f"Could not load policy: {e}")

        # ==================================================================
        # Configure sub-tab (editable settings via API)
        # ==================================================================
        with policy_sub_tabs[1]:
            # Get current policy from API
            current_policy = get_current_policy()
            if not current_policy:
                st.warning("Could not load policy from API. Make sure the API server is running.")
            else:
                # Display current version info
                info_cols = st.columns(4)
                with info_cols[0]:
                    st.metric("Current Version", current_policy.get("version", "N/A"))
                with info_cols[1]:
                    st.metric("Last Changed By", current_policy.get("changed_by", "N/A"))
                with info_cols[2]:
                    created_at = current_policy.get("created_at", "")
                    if created_at:
                        created_at = created_at[:19].replace("T", " ")
                    st.metric("Last Updated", created_at or "N/A")
                with info_cols[3]:
                    policy_hash = current_policy.get("policy_hash", "")[:12]
                    st.metric("Policy Hash", policy_hash + "..." if policy_hash else "N/A")

                st.divider()

                # Settings sub-tabs within Configure
                settings_tabs = st.tabs([
                    "Thresholds",
                    "Rules",
                    "Blocklists",
                    "Allowlists",
                ])

                policy_content = current_policy.get("policy", {})

                # ----------------------------------------------------------
                # Thresholds
                # ----------------------------------------------------------
                with settings_tabs[0]:
                    st.markdown("#### Score Thresholds")
                    st.caption("Configure score thresholds for each decision type. Validation: friction < review < block")

                    config_thresholds = policy_content.get("thresholds", {})

                    with st.form("threshold_form"):
                        threshold_updates = []

                        for score_type in ["risk", "criminal", "friendly"]:
                            st.markdown(f"**{score_type.title()} Score**")
                            thresh = config_thresholds.get(score_type, {})

                            cols = st.columns(3)
                            with cols[0]:
                                friction = st.slider(
                                    f"Friction Threshold",
                                    min_value=0.0, max_value=1.0,
                                    value=float(thresh.get("friction_threshold", 0.5)),
                                    step=0.05, key=f"{score_type}_friction",
                                    help="Transactions above this score require additional verification"
                                )
                            with cols[1]:
                                review = st.slider(
                                    f"Review Threshold",
                                    min_value=0.0, max_value=1.0,
                                    value=float(thresh.get("review_threshold", 0.7)),
                                    step=0.05, key=f"{score_type}_review",
                                    help="Transactions above this score go to manual review"
                                )
                            with cols[2]:
                                block = st.slider(
                                    f"Block Threshold",
                                    min_value=0.0, max_value=1.0,
                                    value=float(thresh.get("block_threshold", 0.9)),
                                    step=0.05, key=f"{score_type}_block",
                                    help="Transactions above this score are blocked"
                                )

                            if friction >= review or review >= block:
                                st.error(f"Invalid: friction ({friction:.2f}) < review ({review:.2f}) < block ({block:.2f})")

                            threshold_updates.append({
                                "score_type": score_type,
                                "friction_threshold": friction,
                                "review_threshold": review,
                                "block_threshold": block
                            })

                            st.divider()

                        submit_thresholds = st.form_submit_button("Save Thresholds", type="primary")

                        if submit_thresholds:
                            valid = True
                            for update in threshold_updates:
                                if update["friction_threshold"] >= update["review_threshold"]:
                                    valid = False
                                if update["review_threshold"] >= update["block_threshold"]:
                                    valid = False

                            if not valid:
                                st.error("Invalid thresholds. Ensure friction < review < block for all score types.")
                            else:
                                result = update_thresholds(threshold_updates)
                                if "error" in result:
                                    st.error(f"Failed to update thresholds: {result['error']}")
                                else:
                                    st.success(f"Thresholds updated! New version: {result.get('version')}")
                                    st.rerun()

                # ----------------------------------------------------------
                # Rules
                # ----------------------------------------------------------
                with settings_tabs[1]:
                    st.markdown("#### Policy Rules")
                    st.caption("Rules are evaluated in priority order (lower number = higher priority).")

                    config_rules = policy_content.get("rules", [])

                    for rule in sorted(config_rules, key=lambda r: r.get("priority", 100)):
                        rule_id = rule.get("id", "unknown")
                        rule_name = rule.get("name", "Unknown Rule")
                        rule_enabled = rule.get("enabled", True)
                        rule_priority = rule.get("priority", 100)
                        rule_action = rule.get("action", "REVIEW")

                        status_icon = "🟢" if rule_enabled else "🔴"

                        with st.expander(f"{status_icon} **{rule_name}** (Priority: {rule_priority}, Action: {rule_action})"):
                            st.markdown(f"**ID:** `{rule_id}`")
                            st.markdown(f"**Description:** {rule.get('description', 'No description')}")
                            st.markdown(f"**Enabled:** {'Yes' if rule_enabled else 'No'}")

                            if rule.get("friction_type"):
                                st.markdown(f"**Friction Type:** {rule['friction_type']}")
                            if rule.get("review_priority"):
                                st.markdown(f"**Review Priority:** {rule['review_priority']}")

                            st.markdown("**Conditions:**")
                            st.json(rule.get("conditions", {}))

                            col1, col2, col3 = st.columns([1, 1, 2])
                            with col1:
                                if st.button("Delete Rule", key=f"delete_{rule_id}", type="secondary"):
                                    result = delete_policy_rule(rule_id)
                                    if "error" in result:
                                        st.error(f"Failed to delete rule: {result['error']}")
                                    else:
                                        st.success(f"Rule deleted! New version: {result.get('version')}")
                                        st.rerun()

                    st.divider()

                    # Add new rule form
                    st.markdown("#### Add New Rule")
                    with st.form("add_rule_form"):
                        new_rule_id = st.text_input("Rule ID", value="", placeholder="e.g., high_risk_new_user")
                        new_rule_name = st.text_input("Rule Name", value="", placeholder="e.g., High Risk New User")
                        new_rule_description = st.text_area("Description", value="", placeholder="Describe what this rule does")
                        new_rule_priority = st.number_input("Priority", min_value=1, max_value=1000, value=100)
                        new_rule_enabled = st.checkbox("Enabled", value=True)

                        action_col, friction_col = st.columns(2)
                        with action_col:
                            new_rule_action = st.selectbox("Action", ["ALLOW", "FRICTION", "REVIEW", "BLOCK"])
                        with friction_col:
                            new_friction_type = st.selectbox("Friction Type (if FRICTION)", ["None", "3DS", "OTP", "STEP_UP", "CAPTCHA"])

                        new_review_priority = st.selectbox("Review Priority (if REVIEW)", ["None", "LOW", "MEDIUM", "HIGH", "URGENT"])

                        st.markdown("**Conditions (JSON)**")
                        new_conditions = st.text_area(
                            "Conditions",
                            value='{\n  "device_is_emulator": true\n}',
                            height=150,
                            help="Enter conditions as JSON"
                        )

                        submit_rule = st.form_submit_button("Add Rule", type="primary")

                        if submit_rule:
                            if not new_rule_id or not new_rule_name:
                                st.error("Rule ID and Name are required")
                            else:
                                try:
                                    conditions = json.loads(new_conditions)
                                    new_rule = {
                                        "id": new_rule_id,
                                        "name": new_rule_name,
                                        "description": new_rule_description,
                                        "priority": new_rule_priority,
                                        "enabled": new_rule_enabled,
                                        "action": new_rule_action,
                                        "conditions": conditions
                                    }
                                    if new_friction_type != "None":
                                        new_rule["friction_type"] = new_friction_type
                                    if new_review_priority != "None":
                                        new_rule["review_priority"] = new_review_priority

                                    result = add_policy_rule(new_rule)
                                    if "error" in result:
                                        st.error(f"Failed to add rule: {result['error']}")
                                    else:
                                        st.success(f"Rule added! New version: {result.get('version')}")
                                        st.rerun()
                                except json.JSONDecodeError as e:
                                    st.error(f"Invalid JSON in conditions: {e}")

                # ----------------------------------------------------------
                # Blocklists
                # ----------------------------------------------------------
                with settings_tabs[2]:
                    st.markdown("#### Blocklists")
                    st.caption("Transactions matching blocklisted items are automatically blocked.")

                    blocklist_types = {
                        "blocklist_cards": "Card Tokens",
                        "blocklist_devices": "Device IDs",
                        "blocklist_ips": "IP Addresses",
                        "blocklist_users": "User IDs"
                    }

                    for list_type, display_name in blocklist_types.items():
                        st.markdown(f"**{display_name}**")
                        items = policy_content.get(list_type, [])

                        if items:
                            cols = st.columns(6)
                            for i, item in enumerate(items):
                                with cols[i % 6]:
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.code(item[:20] + "..." if len(item) > 20 else item)
                                    with col2:
                                        if st.button("X", key=f"remove_{list_type}_{i}", help="Remove"):
                                            result = remove_from_policy_list(list_type, item)
                                            if "error" not in result:
                                                st.rerun()
                        else:
                            st.markdown("*No items in this list*")

                        col1, col2 = st.columns([3, 1])
                        with col1:
                            new_value = st.text_input(
                                f"Add to {display_name}",
                                key=f"add_{list_type}",
                                placeholder=f"Enter {display_name.lower()[:-1]} to block"
                            )
                        with col2:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("Add", key=f"add_btn_{list_type}", type="primary"):
                                if new_value:
                                    result = add_to_policy_list(list_type, new_value)
                                    if "error" in result:
                                        st.error(f"Failed to add: {result['error']}")
                                    else:
                                        st.success(f"Added! New version: {result.get('version')}")
                                        st.rerun()
                        st.divider()

                # ----------------------------------------------------------
                # Allowlists
                # ----------------------------------------------------------
                with settings_tabs[3]:
                    st.markdown("#### Allowlists")
                    st.caption("Transactions matching allowlisted items skip fraud checks.")

                    allowlist_types = {
                        "allowlist_cards": "Card Tokens",
                        "allowlist_users": "User IDs",
                        "allowlist_services": "Service IDs"
                    }

                    for list_type, display_name in allowlist_types.items():
                        st.markdown(f"**{display_name}**")
                        items = policy_content.get(list_type, [])

                        if items:
                            cols = st.columns(6)
                            for i, item in enumerate(items):
                                with cols[i % 6]:
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.code(item[:20] + "..." if len(item) > 20 else item)
                                    with col2:
                                        if st.button("X", key=f"remove_{list_type}_{i}", help="Remove"):
                                            result = remove_from_policy_list(list_type, item)
                                            if "error" not in result:
                                                st.rerun()
                        else:
                            st.markdown("*No items in this list*")

                        col1, col2 = st.columns([3, 1])
                        with col1:
                            new_value = st.text_input(
                                f"Add to {display_name}",
                                key=f"add_{list_type}",
                                placeholder=f"Enter {display_name.lower()[:-1]} to allow"
                            )
                        with col2:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("Add", key=f"add_btn_{list_type}", type="primary"):
                                if new_value:
                                    result = add_to_policy_list(list_type, new_value)
                                    if "error" in result:
                                        st.error(f"Failed to add: {result['error']}")
                                    else:
                                        st.success(f"Added! New version: {result.get('version')}")
                                        st.rerun()
                        st.divider()

        # ==================================================================
        # Version History sub-tab
        # ==================================================================
        with policy_sub_tabs[2]:
            st.caption("View policy change history and rollback to previous versions if needed.")

            versions = get_policy_versions(limit=50)

            if versions:
                for v in versions:
                    is_active = v.get("is_active", False)
                    version = v.get("version", "N/A")
                    change_type = v.get("change_type", "N/A")
                    change_summary = v.get("change_summary", "")
                    changed_by = v.get("changed_by", "N/A")
                    created_at = v.get("created_at", "")[:19].replace("T", " ")

                    active_badge = "🟢 **ACTIVE**" if is_active else ""

                    with st.expander(f"**v{version}** - {change_type} {active_badge}"):
                        st.markdown(f"**Change Summary:** {change_summary}")
                        st.markdown(f"**Changed By:** {changed_by}")
                        st.markdown(f"**Created At:** {created_at}")

                        if not is_active:
                            if st.button(f"Rollback to v{version}", key=f"rollback_{version}", type="secondary"):
                                result = rollback_policy(version)
                                if "error" in result:
                                    st.error(f"Rollback failed: {result['error']}")
                                else:
                                    st.success(f"Rolled back to v{version}! New version: {result.get('version')}")
                                    st.rerun()
            else:
                st.info("No version history available")


if __name__ == "__main__":
    main()

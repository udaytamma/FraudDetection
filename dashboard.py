"""
Telco/MSP Payment Fraud Detection Platform - Demo Dashboard

Professional-grade Streamlit dashboard for demonstrating and testing
the fraud detection system for Telco/MSP payment fraud.

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
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://fraud_user:fraud_pass@localhost:5432/fraud_detection"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    /* Main container styling */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Card styling */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        padding: 1.5rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    /* Status indicators */
    .status-healthy {
        color: #10b981;
        font-weight: 600;
    }
    .status-degraded {
        color: #f59e0b;
        font-weight: 600;
    }
    .status-down {
        color: #ef4444;
        font-weight: 600;
    }

    /* Decision badges */
    .decision-allow {
        background-color: #10b981;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 9999px;
        font-weight: 600;
        display: inline-block;
    }
    .decision-friction {
        background-color: #f59e0b;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 9999px;
        font-weight: 600;
        display: inline-block;
    }
    .decision-review {
        background-color: #f97316;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 9999px;
        font-weight: 600;
        display: inline-block;
    }
    .decision-block {
        background-color: #ef4444;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 9999px;
        font-weight: 600;
        display: inline-block;
    }

    /* Severity badges */
    .severity-critical {
        background-color: #7f1d1d;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .severity-high {
        background-color: #ef4444;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .severity-medium {
        background-color: #f59e0b;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .severity-low {
        background-color: #6b7280;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Score gauge styling */
    .score-container {
        text-align: center;
        padding: 1rem;
    }

    /* Reason card */
    .reason-card {
        background-color: #f8fafc;
        border-left: 4px solid #ef4444;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }

    /* Header styling */
    .dashboard-header {
        background: linear-gradient(90deg, #1e3a5f 0%, #2d5a87 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 2rem;
    }

    /* Metric box */
    .metric-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f1f5f9;
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Helper Functions
# ============================================================================

def get_api_health() -> dict:
    """Check API health status."""
    try:
        response = httpx.get(f"{API_URL}/health", timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"status": "down", "components": {"redis": False, "postgres": False, "policy": False}}


def get_policy_version() -> dict:
    """Get current policy version."""
    try:
        response = httpx.get(f"{API_URL}/policy/version", timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"version": "N/A", "hash": "N/A"}


def get_current_policy() -> dict:
    """Get current active policy configuration."""
    try:
        response = httpx.get(f"{API_URL}/policy", timeout=5.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {}


def get_policy_versions(limit: int = 50) -> list:
    """Get policy version history."""
    try:
        response = httpx.get(f"{API_URL}/policy/versions", params={"limit": limit}, timeout=5.0)
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
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}: {response.text}"}
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
                amount_cents,
                card_token,
                merchant_id,
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


async def get_analytics_data() -> dict:
    """Get aggregated analytics data."""
    try:
        conn = await asyncpg.connect(POSTGRES_URL)

        # Decision distribution
        decision_dist = await conn.fetch("""
            SELECT decision, COUNT(*) as count
            FROM transaction_evidence
            WHERE captured_at > NOW() - INTERVAL '24 hours'
            GROUP BY decision
        """)

        # Hourly volume
        hourly_volume = await conn.fetch("""
            SELECT
                DATE_TRUNC('hour', captured_at) as hour,
                COUNT(*) as count,
                AVG(processing_time_ms) as avg_latency
            FROM transaction_evidence
            WHERE captured_at > NOW() - INTERVAL '24 hours'
            GROUP BY DATE_TRUNC('hour', captured_at)
            ORDER BY hour
        """)

        # Score distribution
        score_stats = await conn.fetchrow("""
            SELECT
                AVG(risk_score) as avg_risk,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY risk_score) as median_risk,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY risk_score) as p95_risk,
                AVG(processing_time_ms) as avg_latency,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY processing_time_ms) as p99_latency,
                COUNT(*) as total_count
            FROM transaction_evidence
            WHERE captured_at > NOW() - INTERVAL '24 hours'
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

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score * 100,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 14}},
        number={'suffix': "%", 'font': {'size': 24}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#e2e8f0",
            'steps': [
                {'range': [0, 30], 'color': '#d1fae5'},
                {'range': [30, 60], 'color': '#fef3c7'},
                {'range': [60, 80], 'color': '#fed7aa'},
                {'range': [80, 100], 'color': '#fecaca'}
            ],
            'threshold': {
                'line': {'color': "#1e293b", 'width': 2},
                'thickness': 0.75,
                'value': score * 100
            }
        }
    ))

    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        font={'color': "#1e293b"}
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
    # Header
    st.markdown("""
    <div class="dashboard-header">
        <h1 style="margin: 0; font-size: 2rem;">📱 Telco/MSP Payment Fraud Detection</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">
            Real-time payment fraud detection for Mobile &amp; Broadband services with &lt;200ms latency
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar - System Status
    with st.sidebar:
        st.header("System Status")

        health = get_api_health()

        # Overall status
        status = health.get("status", "down")
        if status == "healthy":
            st.success("● System Healthy")
        elif status == "degraded":
            st.warning("● System Degraded")
        else:
            st.error("● System Down")

        # Component status
        st.subheader("Components")
        components = health.get("components", {})

        cols = st.columns(3)
        with cols[0]:
            if components.get("redis"):
                st.markdown("✅ Redis")
            else:
                st.markdown("❌ Redis")
        with cols[1]:
            if components.get("postgres"):
                st.markdown("✅ Postgres")
            else:
                st.markdown("❌ Postgres")
        with cols[2]:
            if components.get("policy"):
                st.markdown("✅ Policy")
            else:
                st.markdown("❌ Policy")

        # Policy version
        policy = get_policy_version()
        st.markdown(f"**Policy Version:** `{policy.get('version', 'N/A')}`")

        st.divider()

        # API Info
        st.subheader("API Endpoints")
        st.code(f"Health: {API_URL}/health")
        st.code(f"Decide: POST {API_URL}/decide")
        st.code(f"Metrics: {API_URL}/metrics")

        st.divider()

        # Quick stats from last decision
        if "last_decision" in st.session_state:
            st.subheader("Last Decision")
            last = st.session_state.last_decision
            st.markdown(get_decision_badge(last.get("decision", "N/A")), unsafe_allow_html=True)
            st.metric("Latency", f"{last.get('processing_time_ms', 0):.1f}ms")

    # Main content tabs
    tabs = st.tabs([
        "🎯 Transaction Simulator",
        "📊 Analytics Dashboard",
        "📜 Decision History",
        "⚙️ Policy Inspector",
        "🔧 Policy Settings"
    ])

    # ==========================================================================
    # Tab 1: Transaction Simulator
    # ==========================================================================
    with tabs[0]:
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

            amount = st.number_input(
                "Amount ($)",
                min_value=0.01,
                value=preset["payload"]["amount_cents"] / 100,
                step=1.0
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

                # Metrics row
                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.metric("Transaction ID", result.get("transaction_id", "N/A")[:16] + "...")
                with metric_cols[1]:
                    st.metric("Processing Time", f"{result.get('processing_time_ms', 0):.2f}ms")
                with metric_cols[2]:
                    st.metric("Policy Version", result.get("policy_version", "N/A"))
                with metric_cols[3]:
                    st.metric("Cached", "Yes" if result.get("is_cached") else "No")

                st.divider()

                # Score gauges
                st.markdown("#### Risk Scores")
                scores = result.get("scores", {})

                gauge_cols = st.columns(4)
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

                # Detailed scores
                with st.expander("Detailed Score Breakdown"):
                    score_cols = st.columns(4)
                    with score_cols[0]:
                        st.metric("Card Testing", f"{scores.get('card_testing_score', 0)*100:.1f}%")
                    with score_cols[1]:
                        st.metric("Velocity", f"{scores.get('velocity_score', 0)*100:.1f}%")
                    with score_cols[2]:
                        st.metric("Geo Anomaly", f"{scores.get('geo_score', 0)*100:.1f}%")
                    with score_cols[3]:
                        st.metric("Confidence", f"{scores.get('confidence', 0)*100:.1f}%")

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
                            <span style="color: #64748b;">{description}</span>
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
                st.info("Submit a transaction to see results")

    # ==========================================================================
    # Tab 2: Analytics Dashboard
    # ==========================================================================
    with tabs[1]:
        st.subheader("Analytics Dashboard")

        # Get analytics data
        try:
            analytics = asyncio.run(get_analytics_data())
        except Exception as e:
            analytics = {"error": str(e)}

        if "error" in analytics:
            st.warning(f"Could not load analytics: {analytics.get('error')}")
            st.info("Submit some transactions first to generate analytics data.")
        else:
            # Key metrics
            stats = analytics.get("score_stats", {})

            metric_cols = st.columns(5)
            with metric_cols[0]:
                st.metric(
                    "Total Transactions (24h)",
                    f"{stats.get('total_count', 0):,}"
                )
            with metric_cols[1]:
                st.metric(
                    "Avg Risk Score",
                    f"{(stats.get('avg_risk', 0) or 0)*100:.1f}%"
                )
            with metric_cols[2]:
                st.metric(
                    "P95 Risk Score",
                    f"{(stats.get('p95_risk', 0) or 0)*100:.1f}%"
                )
            with metric_cols[3]:
                st.metric(
                    "Avg Latency",
                    f"{stats.get('avg_latency', 0) or 0:.1f}ms"
                )
            with metric_cols[4]:
                st.metric(
                    "P99 Latency",
                    f"{stats.get('p99_latency', 0) or 0:.1f}ms"
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
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2)
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
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hourly data available")

            # Latency chart
            st.markdown("#### Latency Over Time")
            if hourly_data:
                df = pd.DataFrame(hourly_data)
                fig = px.line(
                    df,
                    x="hour",
                    y="avg_latency",
                    markers=True,
                    color_discrete_sequence=["#8b5cf6"]
                )
                fig.add_hline(
                    y=200,
                    line_dash="dash",
                    line_color="red",
                    annotation_text="Target: 200ms"
                )
                fig.update_layout(
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis_title="Hour",
                    yaxis_title="Avg Latency (ms)",
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

    # ==========================================================================
    # Tab 3: Decision History
    # ==========================================================================
    with tabs[2]:
        st.subheader("Decision History")

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
            df["latency"] = df["processing_time_ms"].apply(lambda x: f"{x:.1f}ms" if x else "N/A")
            df["time"] = pd.to_datetime(df["captured_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

            # Display table
            st.dataframe(
                df[["transaction_id", "decision", "amount", "risk", "latency", "time"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "transaction_id": st.column_config.TextColumn("Transaction ID", width="medium"),
                    "decision": st.column_config.TextColumn("Decision", width="small"),
                    "amount": st.column_config.TextColumn("Amount", width="small"),
                    "risk": st.column_config.TextColumn("Risk Score", width="small"),
                    "latency": st.column_config.TextColumn("Latency", width="small"),
                    "time": st.column_config.TextColumn("Time", width="medium"),
                }
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
            st.info("No transaction history found. Submit some transactions first.")

    # ==========================================================================
    # Tab 4: Policy Inspector
    # ==========================================================================
    with tabs[3]:
        st.subheader("Policy Inspector")

        # Load policy file
        policy_path = os.path.join(os.path.dirname(__file__), "config", "policy.yaml")

        try:
            import yaml
            with open(policy_path, "r") as f:
                policy = yaml.safe_load(f)

            # Policy version
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Version", policy.get("version", "N/A"))
            with col2:
                st.metric("Default Action", policy.get("default_action", "ALLOW"))

            st.markdown(f"*{policy.get('description', '')}*")

            st.divider()

            # Thresholds
            st.markdown("#### Score Thresholds")
            thresholds = policy.get("thresholds", {})

            thresh_cols = st.columns(3)
            for i, (name, thresh) in enumerate(thresholds.items()):
                with thresh_cols[i % 3]:
                    st.markdown(f"**{name.title()} Score**")
                    st.markdown(f"- Block: ≥ {thresh.get('block_threshold', 0)*100:.0f}%")
                    st.markdown(f"- Review: ≥ {thresh.get('review_threshold', 0)*100:.0f}%")
                    st.markdown(f"- Friction: ≥ {thresh.get('friction_threshold', 0)*100:.0f}%")

            st.divider()

            # Rules
            st.markdown("#### Active Rules")
            rules = policy.get("rules", [])

            for rule in rules:
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
                st.markdown(f"- Cards: {len(policy.get('blocklist_cards', []))} entries")
                st.markdown(f"- Devices: {len(policy.get('blocklist_devices', []))} entries")
                st.markdown(f"- IPs: {len(policy.get('blocklist_ips', []))} entries")
                st.markdown(f"- Users: {len(policy.get('blocklist_users', []))} entries")

            with list_cols[1]:
                st.markdown("#### Allowlists")
                st.markdown(f"- Cards: {len(policy.get('allowlist_cards', []))} entries")
                st.markdown(f"- Users: {len(policy.get('allowlist_users', []))} entries")
                st.markdown(f"- Services: {len(policy.get('allowlist_services', []))} entries")

            # Raw YAML
            with st.expander("Raw Policy YAML"):
                st.code(yaml.dump(policy, default_flow_style=False), language="yaml")

        except Exception as e:
            st.error(f"Could not load policy: {e}")

    # ==========================================================================
    # Tab 5: Policy Settings
    # ==========================================================================
    with tabs[4]:
        st.subheader("Policy Settings")
        st.markdown("*Manage policy configuration with full version control*")

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

            # Sub-tabs for different settings sections
            settings_tabs = st.tabs([
                "📊 Thresholds",
                "📋 Rules",
                "🚫 Blocklists",
                "✅ Allowlists",
                "📜 Version History"
            ])

            policy_content = current_policy.get("policy", {})

            # ------------------------------------------------------------------
            # Thresholds Tab
            # ------------------------------------------------------------------
            with settings_tabs[0]:
                st.markdown("### Score Thresholds")
                st.info("Configure score thresholds for each decision type. Validation: friction < review < block")

                thresholds = policy_content.get("thresholds", {})

                # Create editable form for thresholds
                with st.form("threshold_form"):
                    threshold_updates = []

                    for score_type in ["risk", "criminal", "friendly"]:
                        st.markdown(f"#### {score_type.title()} Score")
                        thresh = thresholds.get(score_type, {})

                        cols = st.columns(3)
                        with cols[0]:
                            friction = st.slider(
                                f"Friction Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("friction_threshold", 0.5)),
                                step=0.05,
                                key=f"{score_type}_friction",
                                help="Transactions above this score require additional verification"
                            )
                        with cols[1]:
                            review = st.slider(
                                f"Review Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("review_threshold", 0.7)),
                                step=0.05,
                                key=f"{score_type}_review",
                                help="Transactions above this score go to manual review"
                            )
                        with cols[2]:
                            block = st.slider(
                                f"Block Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("block_threshold", 0.9)),
                                step=0.05,
                                key=f"{score_type}_block",
                                help="Transactions above this score are blocked"
                            )

                        # Validation check
                        if friction >= review or review >= block:
                            st.error(f"Invalid thresholds for {score_type}: friction ({friction:.2f}) < review ({review:.2f}) < block ({block:.2f})")

                        threshold_updates.append({
                            "score_type": score_type,
                            "friction_threshold": friction,
                            "review_threshold": review,
                            "block_threshold": block
                        })

                        st.divider()

                    submit_thresholds = st.form_submit_button("Save Thresholds", type="primary")

                    if submit_thresholds:
                        # Validate all thresholds
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

            # ------------------------------------------------------------------
            # Rules Tab
            # ------------------------------------------------------------------
            with settings_tabs[1]:
                st.markdown("### Policy Rules")
                st.info("Manage fraud detection rules. Rules are evaluated in priority order (lower = higher priority).")

                rules = policy_content.get("rules", [])

                # Display existing rules
                st.markdown("#### Existing Rules")
                for rule in sorted(rules, key=lambda r: r.get("priority", 100)):
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

                        # Delete button
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

            # ------------------------------------------------------------------
            # Blocklists Tab
            # ------------------------------------------------------------------
            with settings_tabs[2]:
                st.markdown("### Blocklists")
                st.info("Manage blocked entities. Transactions matching blocklisted items are automatically blocked.")

                blocklist_types = {
                    "blocklist_cards": "Card Tokens",
                    "blocklist_devices": "Device IDs",
                    "blocklist_ips": "IP Addresses",
                    "blocklist_users": "User IDs"
                }

                for list_type, display_name in blocklist_types.items():
                    st.markdown(f"#### {display_name}")

                    items = policy_content.get(list_type, [])

                    if items:
                        # Display as chips/tags
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

                    # Add new item
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

            # ------------------------------------------------------------------
            # Allowlists Tab
            # ------------------------------------------------------------------
            with settings_tabs[3]:
                st.markdown("### Allowlists")
                st.info("Manage allowed entities. Transactions matching allowlisted items skip fraud checks.")

                allowlist_types = {
                    "allowlist_cards": "Card Tokens",
                    "allowlist_users": "User IDs",
                    "allowlist_services": "Service IDs"
                }

                for list_type, display_name in allowlist_types.items():
                    st.markdown(f"#### {display_name}")

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

                    # Add new item
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

            # ------------------------------------------------------------------
            # Version History Tab
            # ------------------------------------------------------------------
            with settings_tabs[4]:
                st.markdown("### Version History")
                st.info("View policy change history and rollback to previous versions if needed.")

                versions = get_policy_versions(limit=50)

                if versions:
                    # Version history table
                    for v in versions:
                        is_active = v.get("is_active", False)
                        version = v.get("version", "N/A")
                        change_type = v.get("change_type", "N/A")
                        change_summary = v.get("change_summary", "")
                        changed_by = v.get("changed_by", "N/A")
                        created_at = v.get("created_at", "")[:19].replace("T", " ")

                        # Active version badge
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

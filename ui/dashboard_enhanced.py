"""
Telco/MSP Payment Fraud Detection Platform - Enhanced Dashboard

A production-grade NOC-style dashboard with dark command center aesthetics,
real-time monitoring, and distinctive visual design.

Run: streamlit run ui/dashboard_enhanced.py --server.port 8501
"""

import asyncio
import json
import os
import random
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

# Page configuration - Dark theme NOC style
st.set_page_config(
    page_title="FRAUD OPS // Command Center",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Configuration
API_URL = os.getenv("FRAUD_API_URL", "http://localhost:8000")
METRICS_TOKEN = os.getenv("FRAUD_METRICS_TOKEN", "")
METRICS_HEADERS = {"X-API-Key": METRICS_TOKEN} if METRICS_TOKEN else {}


def fetch_metrics_summary(hours: int = 24) -> Optional[dict]:
    """Fetch live telemetry from the API if available."""
    try:
        resp = httpx.get(
            f"{API_URL}/metrics/summary",
            params={"hours": hours},
            headers=METRICS_HEADERS,
            timeout=2.5,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None


def _aggregate_events_by_hour(events: list[dict]) -> tuple[list[datetime], list[float], list[float], list[int]]:
    """Aggregate telemetry events into hourly averages and p99."""
    buckets: dict[datetime, list[float]] = {}
    for event in events:
        ts = datetime.fromisoformat(event["ts"])
        hour = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, []).append(event["latency_ms"])

    times = sorted(buckets.keys())
    avgs = []
    p99s = []
    counts = []
    for hour in times:
        values = buckets[hour]
        values_sorted = sorted(values)
        index = int(round(0.99 * (len(values_sorted) - 1)))
        p99 = values_sorted[index] if values_sorted else 0
        avgs.append(sum(values) / len(values))
        p99s.append(p99)
        counts.append(len(values))

    return times, avgs, p99s, counts

# =============================================================================
# THEME CONFIGURATION
# =============================================================================
# Initialize theme in session state
if "theme" not in st.session_state:
    st.session_state.theme = "dark"  # Default to dark theme

def get_theme_colors():
    """Get color palette based on current theme."""
    if st.session_state.theme == "dark":
        return {
            "bg_primary": "#0a0e1a",
            "bg_secondary": "#0d1220",
            "bg_tertiary": "#111827",
            "bg_card": "rgba(15, 23, 42, 0.8)",
            "text_primary": "#ffffff",
            "text_secondary": "#e2e8f0",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b",
            "accent_primary": "#00f0ff",
            "accent_secondary": "#7c3aed",
            "alert_red": "#ff3366",
            "success": "#10b981",
            "warning": "#eab308",
            "border": "rgba(0, 240, 255, 0.2)",
            "border_hover": "rgba(0, 240, 255, 0.4)",
        }
    elif st.session_state.theme == "light":
        return {
            "bg_primary": "#f8fafc",
            "bg_secondary": "#f1f5f9",
            "bg_tertiary": "#e2e8f0",
            "bg_card": "rgba(255, 255, 255, 0.9)",
            "text_primary": "#0f172a",
            "text_secondary": "#1e293b",
            "text_muted": "#475569",
            "text_dim": "#64748b",
            "accent_primary": "#0891b2",
            "accent_secondary": "#6366f1",
            "alert_red": "#dc2626",
            "success": "#059669",
            "warning": "#d97706",
            "border": "rgba(8, 145, 178, 0.3)",
            "border_hover": "rgba(8, 145, 178, 0.5)",
        }
    else:  # system - default to dark for now
        return {
            "bg_primary": "#0a0e1a",
            "bg_secondary": "#0d1220",
            "bg_tertiary": "#111827",
            "bg_card": "rgba(15, 23, 42, 0.8)",
            "text_primary": "#ffffff",
            "text_secondary": "#e2e8f0",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b",
            "accent_primary": "#00f0ff",
            "accent_secondary": "#7c3aed",
            "alert_red": "#ff3366",
            "success": "#10b981",
            "warning": "#eab308",
            "border": "rgba(0, 240, 255, 0.2)",
            "border_hover": "rgba(0, 240, 255, 0.4)",
        }

# Get current theme colors
colors = get_theme_colors()

# =============================================================================
# CUSTOM CSS - Theme-Aware Styling
# =============================================================================
# Typography: IBM Plex Mono for data, IBM Plex Sans for headings
# Style: Professional NOC/Financial terminal - clean, authoritative

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

    /* Global theme */
    .stApp {{
        background: linear-gradient(135deg, {colors["bg_primary"]} 0%, {colors["bg_secondary"]} 50%, {colors["bg_tertiary"]} 100%);
    }}

    /* Hide default streamlit elements */
    #MainMenu, footer, header {{visibility: hidden;}}
    .stDeployButton {{display: none;}}

    /* Main container */
    .main .block-container {{
        padding: 1rem 2rem;
        max-width: 100%;
    }}

    /* Theme Toggle Styling */
    .theme-toggle {{
        display: flex;
        gap: 0.5rem;
        align-items: center;
        background: {colors["bg_card"]};
        padding: 0.25rem;
        border-radius: 4px;
        border: 1px solid {colors["border"]};
    }}

    .theme-btn {{
        padding: 0.35rem 0.75rem;
        border: none;
        background: transparent;
        color: {colors["text_muted"]};
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        cursor: pointer;
        border-radius: 3px;
        transition: all 0.2s ease;
    }}

    .theme-btn:hover {{
        background: {colors["border"]};
        color: {colors["text_primary"]};
    }}

    .theme-btn.active {{
        background: {colors["accent_primary"]};
        color: {colors["bg_primary"]};
        font-weight: 600;
    }}

    /* Command Center Header */
    .command-header {{
        background: linear-gradient(90deg, {colors["border"]} 0%, transparent 50%, rgba(255,51,102,0.1) 100%);
        border: 1px solid {colors["border"]};
        border-radius: 0;
        padding: 1.5rem 2rem;
        margin-bottom: 2rem;
        position: relative;
        overflow: hidden;
    }}

    .command-header::before {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, {colors["accent_primary"]}, {colors["accent_secondary"]}, {colors["alert_red"]});
    }}

    .command-header::after {{
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, {colors["border_hover"]}, transparent);
    }}

    .header-title {{
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 2.5rem;
        font-weight: 800;
        color: {colors["text_primary"]};
        margin: 0;
        letter-spacing: 4px;
        text-transform: uppercase;
    }}

    .header-subtitle {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.85rem;
        color: {colors["accent_primary"]};
        margin-top: 0.5rem;
        letter-spacing: 2px;
    }}

    .header-status {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.75rem;
        color: {colors["text_dim"]};
        margin-top: 1rem;
    }}

    /* Metric Cards - Glassmorphism */
    .metric-card {{
        background: {colors["bg_card"]};
        backdrop-filter: blur(10px);
        border: 1px solid {colors["border"]};
        border-radius: 4px;
        padding: 1.5rem;
        position: relative;
        transition: all 0.3s ease;
        min-height: 160px;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        gap: 0.5rem;
    }}

    .metric-card:hover {{
        border-color: {colors["border_hover"]};
        box-shadow: 0 0 30px {colors["border"]};
    }}

    .metric-card::before {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 4px;
        height: 100%;
        background: linear-gradient(180deg, {colors["accent_primary"]}, transparent);
    }}

    .metric-value {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 2.5rem;
        font-weight: 700;
        color: {colors["text_primary"]};
        line-height: 1;
        flex-shrink: 0;
    }}

    .metric-label {{
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 0.75rem;
        color: {colors["text_dim"]};
        text-transform: uppercase;
        letter-spacing: 2px;
        line-height: 1.4;
    }}

    .metric-delta {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
    }}

    .delta-positive {{ color: {colors["success"]}; }}
    .delta-negative {{ color: {colors["alert_red"]}; }}

    /* Decision Badges */
    .decision-allow {{
        background: linear-gradient(135deg, #10b981, #059669);
        color: #ffffff;
        padding: 0.5rem 1.5rem;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 2px;
        border: none;
        display: inline-block;
    }}

    .decision-friction {{
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: #000000;
        padding: 0.5rem 1.5rem;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 2px;
        border: none;
        display: inline-block;
    }}

    .decision-review {{
        background: linear-gradient(135deg, #7c3aed, #5b21b6);
        color: #ffffff;
        padding: 0.5rem 1.5rem;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 2px;
        border: none;
        display: inline-block;
    }}

    .decision-block {{
        background: linear-gradient(135deg, #ff3366, #dc2626);
        color: #ffffff;
        padding: 0.5rem 1.5rem;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 2px;
        border: none;
        display: inline-block;
        animation: pulse-red 2s infinite;
    }}

    @keyframes pulse-red {{
        from, to {{ box-shadow: 0 0 0 0 rgba(255,51,102,0.4); }}
        50%      {{ box-shadow: 0 0 20px 5px rgba(255,51,102,0.2); }}
    }}

    /* Severity badges */
    .severity-critical {{
        background: {colors["alert_red"]};
        color: #ffffff;
        padding: 0.25rem 0.75rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    .severity-high {{
        background: #f97316;
        color: #ffffff;
        padding: 0.25rem 0.75rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    .severity-medium {{
        background: {colors["warning"]};
        color: #000000;
        padding: 0.25rem 0.75rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    .severity-low {{
        background: {colors["text_dim"]};
        color: #ffffff;
        padding: 0.25rem 0.75rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    /* Risk gauge */
    .risk-gauge-container {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        border-radius: 4px;
        padding: 1rem;
    }}

    /* Reason cards */
    .reason-card {{
        background: rgba(255,51,102,0.1);
        border-left: 3px solid {colors["alert_red"]};
        padding: 1rem;
        margin: 0.5rem 0;
        font-family: 'IBM Plex Mono', monospace;
    }}

    .reason-card-warning {{
        background: rgba(234,179,8,0.1);
        border-left: 3px solid {colors["warning"]};
    }}

    /* Transaction form */
    .transaction-form {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        border-radius: 4px;
        padding: 1.5rem;
    }}

    /* Section headers */
    .section-header {{
        font-family: 'IBM Plex Sans', sans-serif;
        font-size: 1.2rem;
        font-weight: 600;
        color: {colors["accent_primary"]};
        text-transform: uppercase;
        letter-spacing: 3px;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid {colors["border"]};
        margin-bottom: 1rem;
    }}

    /* Stats grid */
    .stats-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
    }}

    /* Custom tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        padding: 0.25rem;
    }}

    .stTabs [data-baseweb="tab"] {{
        background: transparent;
        color: {colors["text_dim"]};
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
        letter-spacing: 1px;
        padding: 0.75rem 1.5rem;
        border: none;
    }}

    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {colors["border"]}, {colors["border_hover"]});
        color: {colors["accent_primary"]};
        border-bottom: 2px solid {colors["accent_primary"]};
    }}

    /* Buttons */
    .stButton > button {{
        background: linear-gradient(135deg, {colors["accent_primary"]}, {colors["accent_secondary"]});
        color: {colors["bg_primary"]};
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        letter-spacing: 1px;
        border: none;
        border-radius: 0;
        padding: 0.75rem 2rem;
        transition: all 0.3s ease;
    }}

    .stButton > button:hover {{
        box-shadow: 0 0 20px {colors["border"]};
        transform: translateY(-1px);
    }}

    /* Select boxes */
    .stSelectbox > div > div {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        color: {colors["text_primary"]};
        font-family: 'IBM Plex Mono', monospace;
    }}

    /* Number inputs */
    .stNumberInput > div > div > input {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        color: {colors["text_primary"]};
        font-family: 'IBM Plex Mono', monospace;
    }}

    /* Text inputs */
    .stTextInput > div > div > input {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        color: {colors["text_primary"]};
        font-family: 'IBM Plex Mono', monospace;
    }}

    /* Expander */
    .streamlit-expanderHeader {{
        background: {colors["bg_card"]};
        border: 1px solid {colors["border"]};
        color: {colors["accent_primary"]};
        font-family: 'IBM Plex Mono', monospace;
    }}

    /* Status indicators */
    .status-online {{
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: {colors["success"]};
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
    }}

    .status-online::before {{
        content: '';
        width: 8px;
        height: 8px;
        background: {colors["success"]};
        border-radius: 50%;
        animation: pulse-green 2s infinite;
    }}

    @keyframes pulse-green {{
        from, to {{ box-shadow: 0 0 0 0 rgba(16,185,129,0.7); }}
        50%      {{ box-shadow: 0 0 10px 5px rgba(16,185,129,0.3); }}
    }}

    .status-offline {{
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: {colors["alert_red"]};
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
    }}

    .status-offline::before {{
        content: '';
        width: 8px;
        height: 8px;
        background: {colors["alert_red"]};
        border-radius: 50%;
    }}

    /* Live clock */
    .live-clock {{
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.5rem;
        color: {colors["accent_primary"]};
        text-shadow: 0 0 10px {colors["border"]};
    }}

    /* Scan lines effect (subtle) */
    .scan-lines::after {{
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0,0,0,0.03) 2px,
            rgba(0,0,0,0.03) 4px
        );
        pointer-events: none;
        z-index: 9999;
    }}

    /* Data table */
    .dataframe {{
        background: {colors["bg_card"]} !important;
        color: {colors["text_primary"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.8rem !important;
    }}

    .dataframe th {{
        background: {colors["border"]} !important;
        color: {colors["accent_primary"]} !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
    }}

    .dataframe td {{
        border-color: {colors["border"]} !important;
    }}

    /* Scrollbar */
    ::-webkit-scrollbar {{
        width: 8px;
        height: 8px;
    }}

    ::-webkit-scrollbar-track {{
        background: {colors["bg_primary"]};
    }}

    ::-webkit-scrollbar-thumb {{
        background: {colors["border"]};
        border-radius: 4px;
    }}

    ::-webkit-scrollbar-thumb:hover {{
        background: {colors["border_hover"]};
    }}

    /* Form Labels - CRITICAL for readability */
    .stSelectbox label,
    .stNumberInput label,
    .stTextInput label,
    .stCheckbox label,
    .stRadio label,
    .stSlider label,
    .stTextArea label,
    label {{
        color: {colors["text_muted"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.5px !important;
    }}

    /* Checkbox text specifically */
    .stCheckbox span {{
        color: {colors["text_secondary"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    /* Checkbox container */
    .stCheckbox > label {{
        color: {colors["text_secondary"]} !important;
    }}

    /* Radio button text */
    .stRadio > div > label {{
        color: {colors["text_secondary"]} !important;
    }}

    /* Small helper text under inputs */
    .stTextInput div[data-testid="stMarkdownContainer"] p,
    .stSelectbox div[data-testid="stMarkdownContainer"] p,
    .stNumberInput div[data-testid="stMarkdownContainer"] p {{
        color: {colors["text_dim"]} !important;
        font-size: 0.75rem !important;
    }}

    /* Markdown text in general */
    .stMarkdown p, .stMarkdown li {{
        color: {colors["text_secondary"]} !important;
    }}

    /* Info/warning boxes */
    .stAlert {{
        background: {colors["border"]} !important;
        border: 1px solid {colors["border_hover"]} !important;
        color: {colors["accent_primary"]} !important;
    }}

    .stAlert p {{
        color: {colors["accent_primary"]} !important;
    }}

    /* Caption text */
    .stCaption {{
        color: {colors["text_dim"]} !important;
    }}

    /* Expander content text */
    .streamlit-expanderContent {{
        color: {colors["text_secondary"]} !important;
    }}

    /* Expander header - CRITICAL for readability */
    .streamlit-expanderHeader {{
        color: {colors["text_primary"]} !important;
        font-weight: 600 !important;
        background: {colors["bg_card"]} !important;
        border: 1px solid {colors["border"]} !important;
    }}

    .streamlit-expanderHeader:hover {{
        background: {colors["border"]} !important;
        border-color: {colors["border_hover"]} !important;
    }}

    .streamlit-expanderHeader p {{
        color: {colors["text_primary"]} !important;
        font-weight: 600 !important;
    }}

    /* Expander using data-testid (newer Streamlit versions) */
    [data-testid="stExpander"] {{
        border: 1px solid {colors["border"]} !important;
        background: {colors["bg_card"]} !important;
    }}

    [data-testid="stExpander"] summary {{
        color: {colors["text_primary"]} !important;
        font-weight: 600 !important;
    }}

    [data-testid="stExpander"] summary span {{
        color: {colors["text_primary"]} !important;
    }}

    [data-testid="stExpander"] summary p {{
        color: {colors["text_primary"]} !important;
    }}

    /* Expander details/summary elements */
    details summary {{
        color: {colors["text_primary"]} !important;
    }}

    details summary span {{
        color: {colors["text_secondary"]} !important;
    }}

    /* Expander icon */
    [data-testid="stExpander"] svg {{
        fill: {colors["accent_primary"]} !important;
        stroke: {colors["accent_primary"]} !important;
    }}

    /* Widget labels (newer Streamlit) */
    [data-testid="stWidgetLabel"] {{
        color: {colors["text_muted"]} !important;
    }}

    [data-testid="stWidgetLabel"] p {{
        color: {colors["text_muted"]} !important;
    }}

    /* Slider labels and values */
    .stSlider label,
    .stSlider [data-testid="stWidgetLabel"] {{
        color: {colors["text_secondary"]} !important;
    }}

    .stSlider [data-testid="stThumbValue"] {{
        color: {colors["accent_primary"]} !important;
        font-weight: 600 !important;
    }}

    /* Slider track styling */
    .stSlider [data-baseweb="slider"] {{
        background: {colors["border"]} !important;
    }}

    /* Form submit button */
    .stFormSubmitButton button {{
        background: linear-gradient(135deg, {colors["accent_primary"]}, {colors["accent_secondary"]}) !important;
        color: {colors["bg_primary"]} !important;
        font-weight: 700 !important;
    }}

    /* Metric widget text */
    [data-testid="stMetricValue"] {{
        color: {colors["text_primary"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    [data-testid="stMetricLabel"] {{
        color: {colors["text_muted"]} !important;
    }}

    [data-testid="stMetricDelta"] {{
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    /* Table and markdown table styling */
    .stMarkdown table {{
        background: {colors["bg_card"]} !important;
        border-collapse: collapse !important;
    }}

    .stMarkdown th {{
        background: {colors["border"]} !important;
        color: {colors["accent_primary"]} !important;
        padding: 0.75rem !important;
        border: 1px solid {colors["border"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    .stMarkdown td {{
        color: {colors["text_secondary"]} !important;
        padding: 0.75rem !important;
        border: 1px solid {colors["border"]} !important;
        font-family: 'IBM Plex Mono', monospace !important;
    }}

    /* Bold text in markdown */
    .stMarkdown strong {{
        color: {colors["text_primary"]} !important;
    }}

    /* Code blocks */
    .stMarkdown code {{
        background: {colors["border"]} !important;
        color: {colors["accent_primary"]} !important;
        padding: 0.2rem 0.4rem !important;
        border-radius: 3px !important;
    }}

    /* Horizontal rule */
    .stMarkdown hr {{
        border-color: {colors["border"]} !important;
    }}

    /* Headers in markdown */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{
        color: {colors["text_primary"]} !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
    }}

    /* Plotly chart backgrounds */
    .js-plotly-plot .plotly .main-svg {{
        background: transparent !important;
    }}

    /* Divider line */
    [data-testid="stHorizontalBlock"] hr {{
        border-color: {colors["border"]} !important;
    }}

    /* Success/Error/Warning messages */
    .stSuccess {{
        background: rgba(16, 185, 129, 0.15) !important;
        border: 1px solid {colors["success"]} !important;
        color: {colors["success"]} !important;
    }}

    .stSuccess p {{
        color: {colors["success"]} !important;
    }}

    .stError {{
        background: rgba(255, 51, 102, 0.15) !important;
        border: 1px solid {colors["alert_red"]} !important;
        color: {colors["alert_red"]} !important;
    }}

    .stError p {{
        color: {colors["alert_red"]} !important;
    }}

    .stWarning {{
        background: rgba(234, 179, 8, 0.15) !important;
        border: 1px solid {colors["warning"]} !important;
        color: {colors["warning"]} !important;
    }}

    .stWarning p {{
        color: {colors["warning"]} !important;
    }}

    /* Nested tabs */
    .stTabs [data-baseweb="tab-panel"] {{
        background: transparent !important;
    }}

    /* Help tooltip text */
    [data-testid="stTooltipContent"] {{
        background: {colors["bg_card"]} !important;
        color: {colors["text_secondary"]} !important;
        border: 1px solid {colors["border"]} !important;
    }}

    /* JSON display */
    .stJson {{
        background: {colors["bg_card"]} !important;
    }}

    /* Select dropdown options */
    [data-baseweb="menu"] {{
        background: {colors["bg_card"]} !important;
        border: 1px solid {colors["border"]} !important;
    }}

    [data-baseweb="menu"] li {{
        color: {colors["text_secondary"]} !important;
    }}

    [data-baseweb="menu"] li:hover {{
        background: {colors["border"]} !important;
    }}

    /* Compact reload button styling */
    .reload-btn {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.4rem 0.8rem;
        background: {colors["bg_tertiary"]};
        border: 1px solid {colors["border"]};
        border-radius: 4px;
        color: {colors["text_muted"]};
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        cursor: pointer;
        transition: all 0.2s ease;
    }}

    .reload-btn:hover {{
        background: {colors["border"]};
        border-color: {colors["border_hover"]};
        color: {colors["accent_primary"]};
    }}

    /* Make small buttons less bulky */
    .small-btn .stButton > button {{
        padding: 0.35rem 0.75rem !important;
        font-size: 0.75rem !important;
        min-height: unset !important;
    }}

    /* Theme toggle buttons - compact pill style */
    [data-testid="column"]:has([data-testid="stButton"][aria-label*="theme"]) .stButton > button,
    [data-testid="stButton"][data-testid*="theme"] button {{
        padding: 0.2rem 0.4rem !important;
        min-height: unset !important;
        min-width: unset !important;
        font-size: 0.7rem !important;
        border-radius: 4px !important;
        background: transparent !important;
        border: 1px solid {colors["border"]} !important;
        color: {colors["text_muted"]} !important;
    }}

    /* Theme button containers - make them tight */
    [data-testid="column"]:last-child [data-testid="column"] {{
        padding: 0 !important;
    }}

    /* Active theme button */
    [data-testid="stButton"][data-testid*="theme"] button[kind="primary"],
    button[kind="primary"][data-testid*="theme"] {{
        background: {colors["accent_primary"]} !important;
        color: {colors["bg_primary"]} !important;
        border-color: {colors["accent_primary"]} !important;
    }}

    /* Theme buttons hover */
    [data-testid="stButton"] button:hover {{
        border-color: {colors["border_hover"]} !important;
    }}

    /* Specific styling for the rightmost column theme buttons */
    div[data-testid="column"]:last-of-type .stButton > button {{
        padding: 0.15rem 0.35rem !important;
        min-height: 24px !important;
        font-size: 0.65rem !important;
    }}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Helper Functions
# =============================================================================

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


def get_policy_versions(limit: int = 50) -> list:
    """Get policy version history."""
    try:
        response = httpx.get(f"{API_URL}/policy/versions", params={"limit": limit}, timeout=5.0)
        if response.status_code == 200:
            return response.json().get("versions", [])
    except Exception:
        pass
    return []


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
        response = httpx.post(f"{API_URL}/decide", json=payload, timeout=10.0)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}


def get_decision_badge(decision: str) -> str:
    """Get HTML badge for decision."""
    badges = {
        "ALLOW": '<span class="decision-allow">✓ ALLOW</span>',
        "FRICTION": '<span class="decision-friction">⚡ FRICTION</span>',
        "REVIEW": '<span class="decision-review">👁 REVIEW</span>',
        "BLOCK": '<span class="decision-block">✕ BLOCK</span>',
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


def create_risk_gauge(score: float, title: str) -> go.Figure:
    """Create a cyberpunk-style risk gauge."""
    # Color based on score
    if score < 0.3:
        bar_color = "#10b981"
        bg_colors = ["#064e3b", "#065f46", "#047857", "#10b981"]
    elif score < 0.6:
        bar_color = "#eab308"
        bg_colors = ["#713f12", "#854d0e", "#a16207", "#eab308"]
    elif score < 0.8:
        bar_color = "#f97316"
        bg_colors = ["#7c2d12", "#9a3412", "#c2410c", "#f97316"]
    else:
        bar_color = "#ff3366"
        bg_colors = ["#7f1d1d", "#991b1b", "#dc2626", "#ff3366"]

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score * 100,
        number={
            'suffix': "%",
            'font': {'size': 36, 'family': 'IBM Plex Mono', 'color': '#ffffff'}
        },
        title={
            'text': title,
            'font': {'size': 12, 'family': 'IBM Plex Sans', 'color': '#64748b'}
        },
        gauge={
            'axis': {
                'range': [0, 100],
                'tickwidth': 1,
                'tickcolor': '#1e293b',
                'tickfont': {'color': '#475569', 'family': 'IBM Plex Mono', 'size': 10}
            },
            'bar': {'color': bar_color, 'thickness': 0.8},
            'bgcolor': '#0f172a',
            'borderwidth': 2,
            'bordercolor': 'rgba(0,240,255,0.3)',
            'steps': [
                {'range': [0, 30], 'color': 'rgba(16,185,129,0.2)'},
                {'range': [30, 60], 'color': 'rgba(234,179,8,0.2)'},
                {'range': [60, 80], 'color': 'rgba(249,115,22,0.2)'},
                {'range': [80, 100], 'color': 'rgba(255,51,102,0.2)'}
            ],
            'threshold': {
                'line': {'color': '#00f0ff', 'width': 3},
                'thickness': 0.8,
                'value': score * 100
            }
        }
    ))

    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': '#ffffff'}
    )

    return fig


def create_decision_donut(data: dict) -> go.Figure:
    """Create a decision distribution donut chart."""
    if not data:
        data = {"ALLOW": 85, "FRICTION": 8, "REVIEW": 5, "BLOCK": 2}

    labels = list(data.keys())
    values = list(data.values())
    colors = {
        "ALLOW": "#10b981",
        "FRICTION": "#eab308",
        "REVIEW": "#7c3aed",
        "BLOCK": "#ff3366"
    }

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.7,
        marker_colors=[colors.get(l, "#64748b") for l in labels],
        textinfo='percent',
        textposition='outside',
        textfont={'family': 'IBM Plex Mono', 'size': 12, 'color': '#ffffff'},
        hovertemplate='<b>%{label}</b><br>%{value} transactions<br>%{percent}<extra></extra>'
    )])

    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font={'family': 'IBM Plex Mono', 'size': 10, 'color': '#94a3b8'}
        ),
        margin=dict(l=20, r=20, t=20, b=60),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        annotations=[dict(
            text='<b>DECISIONS</b>',
            x=0.5, y=0.5,
            font={'size': 14, 'family': 'IBM Plex Sans', 'color': '#00f0ff'},
            showarrow=False
        )]
    )

    return fig


def create_latency_chart(hours: int = 24) -> go.Figure:
    """Create a latency over time chart with SLA line."""
    summary = fetch_metrics_summary(hours=hours)
    if summary and summary.get("events"):
        times, latencies, p99_latencies, _ = _aggregate_events_by_hour(summary["events"])
    else:
        # Fallback to mock data for demo
        times = [datetime.now() - timedelta(hours=i) for i in range(hours, 0, -1)]
        latencies = [random.gauss(45, 15) for _ in range(hours)]
        p99_latencies = [l * 2.5 for l in latencies]

    fig = go.Figure()

    # P99 area
    fig.add_trace(go.Scatter(
        x=times,
        y=p99_latencies,
        fill='tozeroy',
        fillcolor='rgba(124,58,237,0.2)',
        line=dict(color='rgba(124,58,237,0.5)', width=1),
        name='P99',
        hovertemplate='P99: %{y:.1f}ms<extra></extra>'
    ))

    # Avg line
    fig.add_trace(go.Scatter(
        x=times,
        y=latencies,
        mode='lines',
        line=dict(color='#00f0ff', width=2),
        name='Average',
        hovertemplate='Avg: %{y:.1f}ms<extra></extra>'
    ))

    # SLA line
    fig.add_hline(
        y=200,
        line_dash="dash",
        line_color="#ff3366",
        annotation_text="SLA: 200ms",
        annotation_font={'family': 'IBM Plex Mono', 'size': 10, 'color': '#ff3366'}
    )

    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            tickfont={'family': 'IBM Plex Mono', 'size': 10, 'color': '#64748b'},
            linecolor='rgba(0,240,255,0.2)'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(0,240,255,0.1)',
            tickfont={'family': 'IBM Plex Mono', 'size': 10, 'color': '#64748b'},
            title='Latency (ms)',
            title_font={'family': 'IBM Plex Sans', 'size': 12, 'color': '#64748b'}
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font={'family': 'IBM Plex Mono', 'size': 10, 'color': '#94a3b8'}
        ),
        margin=dict(l=50, r=20, t=40, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode='x unified'
    )

    return fig


def create_volume_chart(hours: int = 24) -> go.Figure:
    """Create a transaction volume bar chart."""
    summary = fetch_metrics_summary(hours=hours)
    if summary and summary.get("events"):
        times, _, _, volumes = _aggregate_events_by_hour(summary["events"])
    else:
        times = [datetime.now() - timedelta(hours=i) for i in range(hours, 0, -1)]
        volumes = [random.randint(500, 2000) for _ in range(hours)]

    fig = go.Figure(data=[
        go.Bar(
            x=times,
            y=volumes,
            marker=dict(
                color=volumes,
                colorscale=[[0, '#0891b2'], [0.5, '#00f0ff'], [1, '#22d3ee']],
                line=dict(width=0)
            ),
            hovertemplate='%{y:,} transactions<extra></extra>'
        )
    ])

    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            tickfont={'family': 'IBM Plex Mono', 'size': 10, 'color': '#64748b'},
            linecolor='rgba(0,240,255,0.2)'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(0,240,255,0.1)',
            tickfont={'family': 'IBM Plex Mono', 'size': 10, 'color': '#64748b'},
            title='Transactions',
            title_font={'family': 'IBM Plex Sans', 'size': 12, 'color': '#64748b'}
        ),
        margin=dict(l=50, r=20, t=20, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        bargap=0.3
    )

    return fig


# =============================================================================
# Transaction Presets
# =============================================================================

TRANSACTION_PRESETS = {
    "SIM Activation (Normal)": {
        "description": "Legitimate SIM activation from established subscriber",
        "risk_level": "LOW",
        "payload": {
            "amount_cents": 2500,
            "card_bin": "411111",
            "card_last_four": "1234",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "event_subtype": "sim_activation",
            "account_age_days": 365,
            "is_guest": False,
            "channel": "mobile",
            "device": {"is_emulator": False, "is_rooted": False},
            "geo": {"country_code": "US", "is_vpn": False, "is_tor": False, "is_datacenter": False},
            "verification": {"avs_result": "Y", "cvv_result": "M"}
        }
    },
    "SIM Farm Attack": {
        "description": "Rapid SIM activations with same card (SIM farm setup)",
        "risk_level": "CRITICAL",
        "payload": {
            "amount_cents": 0,
            "card_bin": "411111",
            "card_last_four": "9999",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "event_subtype": "sim_activation",
            "account_age_days": 1,
            "is_guest": True,
            "channel": "web",
            "device": {"is_emulator": True, "is_rooted": False},
            "geo": {"country_code": "US", "is_vpn": True, "is_tor": False, "is_datacenter": True},
            "verification": {"avs_result": "N", "cvv_result": "N"}
        }
    },
    "Card Testing (Topup)": {
        "description": "Small topups to test stolen card validity",
        "risk_level": "HIGH",
        "payload": {
            "amount_cents": 500,
            "card_bin": "411111",
            "card_last_four": "8888",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_prepaid_001",
            "service_type": "mobile",
            "event_subtype": "topup",
            "account_age_days": 1,
            "is_guest": True,
            "channel": "web",
            "device": {"is_emulator": False, "is_rooted": False},
            "geo": {"country_code": "US", "is_vpn": True, "is_tor": False, "is_datacenter": True},
            "verification": {"avs_result": "N", "cvv_result": "N"}
        }
    },
    "Device Upgrade Fraud": {
        "description": "Subsidized device purchase from new subscriber",
        "risk_level": "HIGH",
        "payload": {
            "amount_cents": 99900,
            "card_bin": "555555",
            "card_last_four": "4444",
            "card_brand": "Mastercard",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "event_subtype": "device_upgrade",
            "account_age_days": 7,
            "is_guest": False,
            "channel": "web",
            "device": {"is_emulator": False, "is_rooted": False},
            "geo": {"country_code": "US", "is_vpn": False, "is_tor": False, "is_datacenter": False},
            "verification": {"avs_result": "Y", "cvv_result": "M"}
        }
    },
    "SIM Swap (Account Takeover)": {
        "description": "SIM swap request from unexpected location",
        "risk_level": "CRITICAL",
        "payload": {
            "amount_cents": 0,
            "card_bin": "411111",
            "card_last_four": "5678",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "event_subtype": "sim_swap",
            "account_age_days": 180,
            "is_guest": False,
            "channel": "call_center",
            "device": {"is_emulator": False, "is_rooted": False},
            "geo": {"country_code": "NG", "is_vpn": False, "is_tor": False, "is_datacenter": False},
            "verification": {"avs_result": "N", "cvv_result": "M"}
        }
    },
    "IRSF Setup (International Enable)": {
        "description": "International roaming enable from Tor exit",
        "risk_level": "CRITICAL",
        "payload": {
            "amount_cents": 5000,
            "card_bin": "411111",
            "card_last_four": "7777",
            "card_brand": "Visa",
            "card_type": "credit",
            "card_country": "US",
            "service_id": "mobile_postpaid_001",
            "service_type": "mobile",
            "event_subtype": "international_enable",
            "account_age_days": 14,
            "is_guest": False,
            "channel": "web",
            "device": {"is_emulator": False, "is_rooted": True},
            "geo": {"country_code": "DE", "is_vpn": True, "is_tor": True, "is_datacenter": True},
            "verification": {"avs_result": "N", "cvv_result": "N"}
        }
    },
}


# =============================================================================
# Main Dashboard
# =============================================================================

def main():
    # Get current colors
    colors = get_theme_colors()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Theme icons for the toggle
    theme_icons = {"dark": "●", "light": "○", "system": "◐"}
    current_icon = theme_icons[st.session_state.theme]

    # Command Center Header with integrated theme toggle
    st.markdown(f"""
    <div class="command-header">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <h1 class="header-title">FRAUD OPS</h1>
                <p class="header-subtitle">// TELCO PAYMENT FRAUD DETECTION COMMAND CENTER</p>
            </div>
            <div style="text-align: right;">
                <div class="live-clock">{current_time}</div>
                <p class="header-status">SYSTEM STATUS: MONITORING</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # System status bar with theme toggle
    health = get_api_health()
    policy = get_policy_version()

    status_cols = st.columns([1, 1, 1, 1, 1.5, 1.5, 1])

    with status_cols[0]:
        if health.get("status") == "healthy":
            st.markdown('<span class="status-online">API ONLINE</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-offline">API OFFLINE</span>', unsafe_allow_html=True)

    with status_cols[1]:
        if health.get("components", {}).get("redis"):
            st.markdown('<span class="status-online">REDIS</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-offline">REDIS</span>', unsafe_allow_html=True)

    with status_cols[2]:
        if health.get("components", {}).get("postgres"):
            st.markdown('<span class="status-online">POSTGRES</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-offline">POSTGRES</span>', unsafe_allow_html=True)

    with status_cols[3]:
        if health.get("components", {}).get("policy"):
            st.markdown('<span class="status-online">POLICY</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-offline">POLICY</span>', unsafe_allow_html=True)

    with status_cols[4]:
        st.markdown(f"<span style=\"font-family: 'IBM Plex Mono', monospace; color: {colors['text_dim']}; font-size: 0.8rem;\">POLICY v{policy.get('version', 'N/A')}</span>", unsafe_allow_html=True)

    with status_cols[5]:
        st.markdown(f"<span style=\"font-family: 'IBM Plex Mono', monospace; color: {colors['text_dim']}; font-size: 0.8rem;\">HASH: {policy.get('hash', 'N/A')[:12]}...</span>", unsafe_allow_html=True)

    # Subtle theme toggle - small pill buttons
    with status_cols[6]:
        theme_col1, theme_col2, theme_col3 = st.columns(3)
        with theme_col1:
            if st.button("●", key="theme_dark", help="Dark theme",
                        type="primary" if st.session_state.theme == "dark" else "secondary"):
                if st.session_state.theme != "dark":
                    st.session_state.theme = "dark"
                    st.rerun()
        with theme_col2:
            if st.button("○", key="theme_light", help="Light theme",
                        type="primary" if st.session_state.theme == "light" else "secondary"):
                if st.session_state.theme != "light":
                    st.session_state.theme = "light"
                    st.rerun()
        with theme_col3:
            if st.button("◐", key="theme_system", help="System theme",
                        type="primary" if st.session_state.theme == "system" else "secondary"):
                if st.session_state.theme != "system":
                    st.session_state.theme = "system"
                    st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Main tabs
    tabs = st.tabs([
        "◉ REAL-TIME MONITOR",
        "◎ TRANSACTION SIMULATOR",
        "◌ ANALYTICS",
        "⚙ POLICY CONFIG"
    ])

    # ==========================================================================
    # Tab 1: Real-Time Monitor
    # ==========================================================================
    with tabs[0]:
        # Key metrics row
        st.markdown('<div class="section-header">KEY PERFORMANCE INDICATORS</div>', unsafe_allow_html=True)

        metric_cols = st.columns(5)

        with metric_cols[0]:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value" style="color: #00f0ff;">12.4K</div>
                <div class="metric-label">TRANSACTIONS / HOUR</div>
                <div class="metric-delta delta-positive">↑ 8.2% vs last hour</div>
            </div>
            """, unsafe_allow_html=True)

        with metric_cols[1]:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value" style="color: #10b981;">42ms</div>
                <div class="metric-label">AVG LATENCY</div>
                <div class="metric-delta delta-positive">↓ 12ms improvement</div>
            </div>
            """, unsafe_allow_html=True)

        with metric_cols[2]:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value" style="color: #10b981;">97.2%</div>
                <div class="metric-label">APPROVAL RATE</div>
                <div class="metric-delta delta-positive">↑ 0.3%</div>
            </div>
            """, unsafe_allow_html=True)

        with metric_cols[3]:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value" style="color: #ff3366;">1.8%</div>
                <div class="metric-label">BLOCK RATE</div>
                <div class="metric-delta delta-negative">↑ 0.2%</div>
            </div>
            """, unsafe_allow_html=True)

        with metric_cols[4]:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value" style="color: #eab308;">89ms</div>
                <div class="metric-label">P99 LATENCY</div>
                <div class="metric-delta delta-positive">Under SLA</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Charts row
        chart_cols = st.columns([2, 1])

        with chart_cols[0]:
            st.markdown('<div class="section-header">LATENCY PERFORMANCE</div>', unsafe_allow_html=True)
            fig = create_latency_chart()
            st.plotly_chart(fig, use_container_width=True)

        with chart_cols[1]:
            st.markdown('<div class="section-header">DECISION DISTRIBUTION</div>', unsafe_allow_html=True)
            fig = create_decision_donut({})
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Volume chart
        st.markdown('<div class="section-header">TRANSACTION VOLUME (24H)</div>', unsafe_allow_html=True)
        fig = create_volume_chart()
        st.plotly_chart(fig, use_container_width=True)

    # ==========================================================================
    # Tab 2: Transaction Simulator
    # ==========================================================================
    with tabs[1]:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown('<div class="section-header">SUBMIT TRANSACTION</div>', unsafe_allow_html=True)

            # Preset selector
            preset_name = st.selectbox(
                "Attack Scenario",
                options=list(TRANSACTION_PRESETS.keys()),
                help="Select a fraud scenario to simulate"
            )

            preset = TRANSACTION_PRESETS[preset_name]

            # Risk level indicator
            risk_colors = {
                "LOW": "#10b981",
                "MEDIUM": "#eab308",
                "HIGH": "#f97316",
                "CRITICAL": "#ff3366"
            }
            risk_level = preset.get("risk_level", "MEDIUM")

            st.markdown(f"""
            <div style="background: rgba(15,23,42,0.8); border: 1px solid {risk_colors[risk_level]}; padding: 1rem; margin: 1rem 0;">
                <div style="font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: {risk_colors[risk_level]}; text-transform: uppercase; letter-spacing: 2px;">
                    THREAT LEVEL: {risk_level}
                </div>
                <div style="font-family: 'IBM Plex Sans', sans-serif; color: #94a3b8; margin-top: 0.5rem;">
                    {preset['description']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Transaction details
            amount = st.number_input(
                "Amount ($)",
                min_value=0.0,
                value=float(preset["payload"]["amount_cents"] / 100),
                step=1.0
            )

            with st.expander("Advanced Parameters"):
                card_token = st.text_input("Card Token", value=f"card_{uuid4().hex[:12]}")
                user_id = st.text_input("User ID", value=f"user_{uuid4().hex[:8]}")
                is_emulator = st.checkbox("Emulator", value=preset["payload"]["device"]["is_emulator"])
                is_tor = st.checkbox("Tor Exit", value=preset["payload"]["geo"]["is_tor"])
                is_vpn = st.checkbox("VPN", value=preset["payload"]["geo"]["is_vpn"])

            if st.button("⚡ ANALYZE TRANSACTION", use_container_width=True):
                # Build payload
                payload = preset["payload"].copy()
                payload["transaction_id"] = f"txn_{uuid4().hex[:16]}"
                payload["idempotency_key"] = f"idem_{uuid4().hex[:16]}"
                payload["amount_cents"] = int(amount * 100)
                payload["card_token"] = card_token
                payload["user_id"] = user_id
                payload["device"]["is_emulator"] = is_emulator
                payload["geo"]["is_tor"] = is_tor
                payload["geo"]["is_vpn"] = is_vpn

                with st.spinner("Processing..."):
                    result = submit_transaction(payload)

                if "error" not in result:
                    st.session_state.last_decision = result
                    st.success("Transaction analyzed!")
                else:
                    st.error(f"Error: {result['error']}")

        with col2:
            st.markdown('<div class="section-header">ANALYSIS RESULT</div>', unsafe_allow_html=True)

            if "last_decision" in st.session_state:
                result = st.session_state.last_decision
                decision = result.get("decision", "N/A")

                # Decision badge
                st.markdown(f"### {get_decision_badge(decision)}", unsafe_allow_html=True)

                # Quick stats
                stat_cols = st.columns(3)
                with stat_cols[0]:
                    st.metric("Processing Time", f"{result.get('processing_time_ms', 0):.2f}ms")
                with stat_cols[1]:
                    st.metric("Policy Version", result.get("policy_version", "N/A"))
                with stat_cols[2]:
                    st.metric("Cached", "Yes" if result.get("is_cached") else "No")

                st.markdown("<br>", unsafe_allow_html=True)

                # Risk gauges
                st.markdown('<div class="section-header">RISK SCORES</div>', unsafe_allow_html=True)
                scores = result.get("scores", {})

                gauge_cols = st.columns(4)
                with gauge_cols[0]:
                    fig = create_risk_gauge(scores.get("risk_score", 0), "OVERALL")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[1]:
                    fig = create_risk_gauge(scores.get("criminal_score", 0), "CRIMINAL")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[2]:
                    fig = create_risk_gauge(scores.get("friendly_fraud_score", 0), "FRIENDLY")
                    st.plotly_chart(fig, use_container_width=True)
                with gauge_cols[3]:
                    fig = create_risk_gauge(scores.get("bot_score", 0), "BOT")
                    st.plotly_chart(fig, use_container_width=True)

                # Triggered reasons
                st.markdown('<div class="section-header">TRIGGERED SIGNALS</div>', unsafe_allow_html=True)
                reasons = result.get("reasons", [])

                if reasons:
                    for reason in reasons:
                        severity = reason.get("severity", "LOW")
                        code = reason.get("code", "UNKNOWN")
                        description = reason.get("description", "")

                        card_class = "reason-card" if severity in ["CRITICAL", "HIGH"] else "reason-card reason-card-warning"

                        st.markdown(f"""
                        <div class="{card_class}">
                            {get_severity_badge(severity)} <strong style="color: #ffffff; margin-left: 0.5rem;">{code}</strong><br/>
                            <span style="color: #94a3b8; font-size: 0.85rem;">{description}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("No risk signals detected")

                # Raw response
                with st.expander("Raw API Response"):
                    st.json(result)
            else:
                st.info("Submit a transaction to see analysis results")

    # ==========================================================================
    # Tab 3: Analytics
    # ==========================================================================
    with tabs[2]:
        st.markdown('<div class="section-header">FRAUD ANALYTICS DASHBOARD</div>', unsafe_allow_html=True)
        st.info("Connect to database to view historical analytics. Demo data shown below.")

        # Mock analytics
        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("Total Transactions (24h)", "298,472", "+12.4%")
        with metric_cols[1]:
            st.metric("Blocked Transactions", "5,369", "-8.2%")
        with metric_cols[2]:
            st.metric("Review Queue", "1,247", "+15.1%")
        with metric_cols[3]:
            st.metric("Est. Fraud Prevented", "$847,293", "+23.7%")

    # ==========================================================================
    # Tab 4: Policy Config
    # ==========================================================================
    with tabs[3]:
        st.markdown('<div class="section-header">POLICY CONFIGURATION</div>', unsafe_allow_html=True)

        if health.get("status") == "healthy":
            # Get full policy config
            current_policy = get_current_policy()
            policy_content = current_policy.get("policy", {})
            thresholds = policy_content.get("thresholds", {})

            # Policy status header
            status_col1, status_col2, status_col3 = st.columns([1, 1, 2])
            with status_col1:
                st.markdown("""
                <div class="metric-card">
                    <div class="metric-label">ACTIVE VERSION</div>
                    <div class="metric-value" style="color: #10b981; font-size: 1.8rem;">v{}</div>
                </div>
                """.format(policy.get("version", "N/A")), unsafe_allow_html=True)

            with status_col2:
                st.markdown("""
                <div class="metric-card">
                    <div class="metric-label">POLICY HASH</div>
                    <div class="metric-value" style="color: #00f0ff; font-size: 1rem;">{}</div>
                </div>
                """.format(policy.get("hash", "N/A")[:16]), unsafe_allow_html=True)

            with status_col3:
                # Compact reload button in right-aligned container
                st.markdown('<div style="display: flex; justify-content: flex-end; align-items: center; height: 100%;">', unsafe_allow_html=True)
                reload_col1, reload_col2, reload_col3 = st.columns([2, 1, 1])
                with reload_col3:
                    if st.button("Reload", key="reload_policy_btn", help="Reload policy from config file"):
                        try:
                            response = httpx.post(f"{API_URL}/policy/reload", timeout=5.0)
                            if response.status_code == 200:
                                st.success("Policy reloaded!")
                                st.rerun()
                            else:
                                st.error(f"Reload failed: {response.text}")
                        except Exception as e:
                            st.error(f"Error: {e}")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Sub-tabs for all policy settings
            policy_tabs = st.tabs([
                "📊 THRESHOLDS",
                "📋 RULES",
                "🚫 BLOCKLISTS",
                "✅ ALLOWLISTS",
                "📜 VERSION HISTORY"
            ])

            # ------------------------------------------------------------------
            # Thresholds Tab with Interactive Sliders
            # ------------------------------------------------------------------
            with policy_tabs[0]:
                st.markdown("Configure score thresholds for each decision type. **Validation:** friction < review < block")

                with st.form("threshold_form"):
                    threshold_updates = []

                    for score_type in ["risk", "criminal", "friendly"]:
                        st.markdown(f"**{score_type.upper()} SCORE**")
                        thresh = thresholds.get(score_type, {})

                        cols = st.columns(3)
                        with cols[0]:
                            friction = st.slider(
                                "Friction Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("friction_threshold", 0.5)),
                                step=0.05,
                                key=f"{score_type}_friction",
                                help="Transactions above this score require additional verification (e.g., 3DS)"
                            )
                        with cols[1]:
                            review = st.slider(
                                "Review Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("review_threshold", 0.7)),
                                step=0.05,
                                key=f"{score_type}_review",
                                help="Transactions above this score go to manual review queue"
                            )
                        with cols[2]:
                            block = st.slider(
                                "Block Threshold",
                                min_value=0.0,
                                max_value=1.0,
                                value=float(thresh.get("block_threshold", 0.9)),
                                step=0.05,
                                key=f"{score_type}_block",
                                help="Transactions above this score are automatically blocked"
                            )

                        # Validation check
                        if friction >= review or review >= block:
                            st.error(f"Invalid: friction ({friction:.2f}) must be < review ({review:.2f}) < block ({block:.2f})")

                        threshold_updates.append({
                            "score_type": score_type,
                            "friction_threshold": friction,
                            "review_threshold": review,
                            "block_threshold": block
                        })

                        st.markdown("---")

                    submit_thresholds = st.form_submit_button("💾 SAVE THRESHOLDS", type="primary", use_container_width=True)

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
                                st.error(f"Failed to update: {result['error']}")
                            else:
                                st.success(f"Thresholds updated! New version: {result.get('version', 'N/A')}")
                                st.rerun()

            # ------------------------------------------------------------------
            # Rules Tab
            # ------------------------------------------------------------------
            with policy_tabs[1]:
                st.markdown("Manage fraud detection rules. Rules are evaluated in priority order (lower = higher priority).")

                rules = policy_content.get("rules", [])

                # Display existing rules
                if rules:
                    for rule in sorted(rules, key=lambda r: r.get("priority", 100)):
                        rule_id = rule.get("id", "unknown")
                        rule_enabled = rule.get("enabled", True)
                        status_icon = "🟢" if rule_enabled else "🔴"

                        with st.expander(f"{status_icon} **{rule.get('name', 'Unknown')}** — Priority: {rule.get('priority', 100)} | Action: {rule.get('action', 'N/A')}"):
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
                            if st.button("🗑️ Delete Rule", key=f"delete_{rule_id}", type="secondary"):
                                result = delete_policy_rule(rule_id)
                                if "error" in result:
                                    st.error(f"Failed to delete: {result['error']}")
                                else:
                                    st.success(f"Rule deleted! New version: {result.get('version')}")
                                    st.rerun()
                else:
                    st.info("No custom rules defined. Default detection rules are active.")

                st.markdown("---")

                # Add new rule form
                st.markdown("**Add New Rule**")
                with st.form("add_rule_form"):
                    new_rule_id = st.text_input("Rule ID", placeholder="e.g., high_risk_new_user")
                    new_rule_name = st.text_input("Rule Name", placeholder="e.g., High Risk New User")
                    new_rule_description = st.text_area("Description", placeholder="Describe what this rule does")
                    new_rule_priority = st.number_input("Priority", min_value=1, max_value=1000, value=100)
                    new_rule_enabled = st.checkbox("Enabled", value=True)

                    action_col, friction_col = st.columns(2)
                    with action_col:
                        new_rule_action = st.selectbox("Action", ["ALLOW", "FRICTION", "REVIEW", "BLOCK"])
                    with friction_col:
                        new_friction_type = st.selectbox("Friction Type", ["None", "3DS", "OTP", "STEP_UP", "CAPTCHA"])

                    new_review_priority = st.selectbox("Review Priority", ["None", "LOW", "MEDIUM", "HIGH", "URGENT"])

                    new_conditions = st.text_area(
                        "Conditions (JSON)",
                        value='{\n  "device_is_emulator": true\n}',
                        height=100
                    )

                    submit_rule = st.form_submit_button("➕ ADD RULE", type="primary", use_container_width=True)

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
            with policy_tabs[2]:
                st.markdown("Manage blocked entities. Transactions matching blocklisted items are **automatically blocked**.")

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
                        cols = st.columns(4)
                        for i, item in enumerate(items):
                            with cols[i % 4]:
                                item_col, btn_col = st.columns([3, 1])
                                with item_col:
                                    st.code(item[:16] + "..." if len(item) > 16 else item)
                                with btn_col:
                                    if st.button("✕", key=f"rm_{list_type}_{i}", help="Remove"):
                                        result = remove_from_policy_list(list_type, item)
                                        if "error" not in result:
                                            st.rerun()
                    else:
                        st.markdown("*No items*")

                    # Add new item
                    add_col, btn_col = st.columns([4, 1])
                    with add_col:
                        new_value = st.text_input(f"Add {display_name}", key=f"add_{list_type}", placeholder=f"Enter value to block", label_visibility="collapsed")
                    with btn_col:
                        if st.button("Add", key=f"add_btn_{list_type}", type="primary"):
                            if new_value:
                                result = add_to_policy_list(list_type, new_value)
                                if "error" in result:
                                    st.error(f"Failed: {result['error']}")
                                else:
                                    st.success(f"Added!")
                                    st.rerun()

                    st.markdown("---")

            # ------------------------------------------------------------------
            # Allowlists Tab
            # ------------------------------------------------------------------
            with policy_tabs[3]:
                st.markdown("Manage allowed entities. Transactions matching allowlisted items **skip fraud checks**.")

                allowlist_types = {
                    "allowlist_cards": "Card Tokens",
                    "allowlist_users": "User IDs",
                    "allowlist_services": "Service IDs"
                }

                for list_type, display_name in allowlist_types.items():
                    st.markdown(f"**{display_name}**")
                    items = policy_content.get(list_type, [])

                    if items:
                        cols = st.columns(4)
                        for i, item in enumerate(items):
                            with cols[i % 4]:
                                item_col, btn_col = st.columns([3, 1])
                                with item_col:
                                    st.code(item[:16] + "..." if len(item) > 16 else item)
                                with btn_col:
                                    if st.button("✕", key=f"rm_{list_type}_{i}", help="Remove"):
                                        result = remove_from_policy_list(list_type, item)
                                        if "error" not in result:
                                            st.rerun()
                    else:
                        st.markdown("*No items*")

                    # Add new item
                    add_col, btn_col = st.columns([4, 1])
                    with add_col:
                        new_value = st.text_input(f"Add {display_name}", key=f"add_{list_type}", placeholder=f"Enter value to allow", label_visibility="collapsed")
                    with btn_col:
                        if st.button("Add", key=f"add_btn_{list_type}", type="primary"):
                            if new_value:
                                result = add_to_policy_list(list_type, new_value)
                                if "error" in result:
                                    st.error(f"Failed: {result['error']}")
                                else:
                                    st.success(f"Added!")
                                    st.rerun()

                    st.markdown("---")

            # ------------------------------------------------------------------
            # Version History Tab
            # ------------------------------------------------------------------
            with policy_tabs[4]:
                st.markdown("View policy change history and rollback to previous versions if needed.")

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

                        with st.expander(f"**v{version}** — {change_type} {active_badge}"):
                            st.markdown(f"**Change Summary:** {change_summary}")
                            st.markdown(f"**Changed By:** {changed_by}")
                            st.markdown(f"**Created At:** {created_at}")

                            if not is_active:
                                if st.button(f"⏪ Rollback to v{version}", key=f"rollback_{version}", type="secondary"):
                                    result = rollback_policy(version)
                                    if "error" in result:
                                        st.error(f"Rollback failed: {result['error']}")
                                    else:
                                        st.success(f"Rolled back to v{version}!")
                                        st.rerun()
                else:
                    st.info("No version history available")
        else:
            st.warning("⚠️ API is offline. Connect to API to manage policy settings.")


if __name__ == "__main__":
    main()

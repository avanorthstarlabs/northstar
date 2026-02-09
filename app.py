from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
import base64
import json
import hashlib
import streamlit as st
from lib.runtime import (
    read_mode, write_mode,
    read_inbox, write_inbox,
    trigger_run,
    latest_proposal_any, latest_review_any,
    output_patterns,
    read_json_file,
    list_matching,
    stat_mtime_iso,
    extract_timestamp,
    read_decision,
    write_decision,
    write_priority_from_proposal,
    promote_priority,
    approval_gate_enabled
)
import streamlit.components.v1 as components
import html as _html
from typing import Iterable
from lib.openclaw_client import generate, chat

APP_ROOT = Path(__file__).parent
LOGO_PATH = APP_ROOT / "assets" / "logo.svg"
ICON_PATH = APP_ROOT / "assets" / "icon.png"
PST = ZoneInfo("America/Los_Angeles")

page_icon = str(ICON_PATH) if ICON_PATH.exists() else ":)"
st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide", page_icon=page_icon, initial_sidebar_state="auto")

# ── Global CSS ───────────────────────────────────────────────────
st.markdown(
    """
    <style>
    :root { 
        --bg: #050705;
        --panel: rgba(7, 12, 7, 0.72);
        --panel-hover: rgba(12, 22, 12, 0.85);
        --accent: #39ff14;
        --accent-soft: rgba(57, 255, 20, 0.18);
        --accent-border: rgba(57, 255, 20, 0.25);
        --text: #eaffea;
        --muted: #9ddc9d;
        --danger: #ff4444;
        --warn: #ffaa00;
    }
    .stApp {
        background: radial-gradient(1200px 800px at 20% 10%, #0a140a 0%, #050705 55%, #030403 100%);
        color: var(--text);
    }
    h1, h2, h3, h4 { color: var(--text); }
    .stMarkdown, .stCaption, .stText, .stTextArea textarea { color: var(--text); }
    .stButton>button {
        background: transparent;
        border: 1px solid var(--accent);
        color: var(--accent);
        box-shadow: 0 0 12px rgba(57,255,20,0.15);
        transition: all 150ms ease;
    }
    .stButton>button:hover {
        background: var(--accent-soft);
        border-color: var(--accent);
        box-shadow: 0 0 20px rgba(57,255,20,0.3);
    }
    div[data-baseweb="select"] > div {
        background: rgba(7, 12, 7, 0.6) !important;
        border-color: var(--accent) !important;
    }
    /* Glass grid & cards */
    .card-title-row{display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:6px;}
    .card-title-row .title{font-weight:700; font-size:1.02rem; color:var(--accent); margin:0;}
    .card-title-row .meta{font-size:0.74rem; color:var(--muted); opacity:0.85; white-space:nowrap;}
    .subtle{font-size:0.78rem;color:var(--muted);line-height:1.6;opacity:0.85;}
    .glass-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:12px 0 20px;}
    .glass-card {
        padding:16px 18px;border-radius:14px;
        background:var(--panel);
        border:1px solid var(--accent-border);
        backdrop-filter: blur(8px);
        box-shadow: 0 6px 24px rgba(0,0,0,0.35);
        transition: border-color 200ms ease, box-shadow 200ms ease;
        overflow: hidden;
    }
    .glass-card:hover {
        border-color: rgba(57,255,20,0.45);
        box-shadow: 0 8px 32px rgba(0,0,0,0.45);
    }
    .glass-title {font-weight:600;font-size:0.95rem;margin-bottom:6px;color:var(--accent);}
    .glass-meta {opacity:0.8;font-size:0.8rem;color:var(--muted);line-height:1.5;}
    .pulse {
        display:inline-block;width:10px;height:10px;border-radius:999px;
        margin-right:8px;background:var(--accent);
        box-shadow:0 0 12px rgba(57,255,20,0.6);
        animation:pulse 1.6s ease-in-out infinite;
    }
    /* Compact data strip */
    .data-strip{
        display:flex; flex-wrap:wrap; gap:10px;
        padding:10px 12px; margin: 8px 0 14px;
        border-radius: 12px;
        background: rgba(7, 12, 7, 0.45);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(6px);
    }
    @keyframes pulse {
        0% {transform:scale(0.9); opacity:0.6;}
        50% {transform:scale(1.2); opacity:1;}
        100% {transform:scale(0.9); opacity:0.6;}
    }
    /* Section dividers */
    .section-header {
        font-size:1.1rem;font-weight:700;color:var(--accent);
        margin:20px 0 8px;padding-bottom:6px;
        border-bottom:1px solid var(--accent-border);
    }
    /* Metric cards */
    [data-testid="stMetricValue"] { color: var(--accent) !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { color: var(--muted) !important; }

    /* ── Tab bar overhaul ─────────────────────────────────────── */
    /* Container strip */
    div[data-baseweb="tab-list"] {
        background: rgba(7, 12, 7, 0.6);
        border: 1px solid var(--accent-border);
        border-radius: 12px;
        padding: 4px 6px;
        gap: 2px;
        backdrop-filter: blur(6px);
        overflow-x: auto;
    }
    /* Individual tab buttons */
    div[data-baseweb="tab-list"] button[data-baseweb="tab"] {
        background: transparent !important;
        border: 1px solid transparent !important;
        border-radius: 8px !important;
        color: var(--muted) !important;
        font-weight: 500 !important;
        font-size: 0.82rem !important;
        padding: 6px 14px !important;
        transition: all 150ms ease !important;
        white-space: nowrap;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]:hover {
        background: var(--accent-soft) !important;
        color: var(--accent) !important;
        border-color: var(--accent-border) !important;
    }
    div[data-baseweb="tab-list"] button[aria-selected="true"] {
        background: var(--accent-soft) !important;
        border: 1px solid var(--accent) !important;
        color: var(--accent) !important;
        font-weight: 700 !important;
        box-shadow: 0 0 14px rgba(57,255,20,0.18) !important;
    }
    /* Kill the default Streamlit blue underline */
    div[data-baseweb="tab-highlight"] {
        display: none !important;
    }
    div[data-baseweb="tab-border"] {
        display: none !important;
    }

    /* ── Scrollable tab strip on small screens ────────────────── */
    div[data-baseweb="tab-list"] {
        scrollbar-width: thin;
        scrollbar-color: var(--accent-border) transparent;
    }
    div[data-baseweb="tab-list"]::-webkit-scrollbar {
        height: 4px;
    }
    div[data-baseweb="tab-list"]::-webkit-scrollbar-thumb {
        background: var(--accent-border);
        border-radius: 4px;
    }

    /* ── Status badge chips ───────────────────────────────────── */
    .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        line-height: 1;
        white-space: nowrap;
    }
    .status-chip.ok {
        background: rgba(57, 255, 20, 0.12);
        border: 1px solid rgba(57, 255, 20, 0.35);
        color: var(--accent);
    }
    .status-chip.warn {
        background: rgba(255, 170, 0, 0.12);
        border: 1px solid rgba(255, 170, 0, 0.35);
        color: var(--warn);
    }
    .status-chip.error {
        background: rgba(255, 68, 68, 0.12);
        border: 1px solid rgba(255, 68, 68, 0.35);
        color: var(--danger);
    }
    .status-chip.neutral {
        background: rgba(157, 220, 157, 0.10);
        border: 1px solid rgba(157, 220, 157, 0.25);
        color: var(--muted);
    }

    /* ── Activity timeline ────────────────────────────────────── */
    .activity-timeline {
        display: flex;
        flex-direction: column;
        gap: 0;
        margin: 8px 0 4px;
    }
    .activity-item {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 8px 0;
        position: relative;
    }
    .activity-item:not(:last-child) {
        border-left: 2px solid var(--accent-border);
        margin-left: 5px;
        padding-left: 16px;
    }
    .activity-item:last-child {
        border-left: 2px solid transparent;
        margin-left: 5px;
        padding-left: 16px;
    }
    .activity-dot {
        position: absolute;
        left: -4px;
        top: 12px;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: var(--accent);
        border: 2px solid var(--bg);
        box-shadow: 0 0 8px rgba(57, 255, 20, 0.4);
        flex-shrink: 0;
    }
    .activity-dot.dimmed {
        background: var(--muted);
        box-shadow: none;
        opacity: 0.5;
    }
    .activity-content {
        flex: 1;
        min-width: 0;
    }
    .activity-ts {
        font-size: 0.72rem;
        color: var(--muted);
        opacity: 0.7;
    }
    .activity-text {
        font-size: 0.82rem;
        color: var(--text);
        line-height: 1.4;
    }

    /* ── Overview hero grid ───────────────────────────────────── */
    .hero-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin: 8px 0 16px;
    }
    .hero-stat {
        padding: 14px 16px;
        border-radius: 12px;
        background: var(--panel);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(8px);
        text-align: center;
    }
    .hero-stat .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--accent);
        line-height: 1.2;
    }
    .hero-stat .label {
        font-size: 0.72rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 4px;
    }
    div[data-baseweb="tab-border"] {
        display: none !important;
    }

    /* ── Section headers ──────────────────────────────────────── */
    .section-header {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--accent);
        margin: 24px 0 10px;
        padding: 0 0 8px;
        border-bottom: 1px solid var(--accent-border);
        letter-spacing: 0.02em;
    }

    /* ── Glass cards v2 ───────────────────────────────────────── */
    .glass-card {
        padding: 18px 20px;
        border-radius: 14px;
        background: var(--panel);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(10px);
        box-shadow: 0 6px 28px rgba(0,0,0,0.4);
        transition: border-color 200ms ease, box-shadow 200ms ease, transform 180ms ease;
    }
    .glass-card:hover {
        border-color: rgba(57,255,20,0.5);
        box-shadow: 0 8px 36px rgba(0,0,0,0.5);
        transform: translateY(-1px);
    }

    /* ── Metric cards ─────────────────────────────────────────── */
    [data-testid="stMetricValue"] {
        color: var(--accent) !important;
        font-weight: 700;
        font-size: 1.6rem !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
    }
    div[data-testid="metric-container"] {
        background: var(--panel);
        border: 1px solid var(--accent-border);
        border-radius: 12px;
        padding: 14px 16px 10px;
        backdrop-filter: blur(6px);
    }

    /* ── Expander styling ─────────────────────────────────────── */
    details[data-testid="stExpander"] {
        border: 1px solid var(--accent-border) !important;
        border-radius: 10px !important;
        background: var(--panel) !important;
    }
    details[data-testid="stExpander"] summary {
        color: var(--text) !important;
        font-weight: 500;
    }

    /* ── Dividers ─────────────────────────────────────────────── */
    hr {
        border: none !important;
        border-top: 1px solid var(--accent-border) !important;
        margin: 20px 0 !important;
    }

    /* ── Sidebar polish ───────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: rgba(5, 8, 5, 0.92) !important;
        border-right: 1px solid var(--accent-border);
    }
    section[data-testid="stSidebar"] .stButton>button {
        font-size: 0.82rem;
    }

    /* ── Text area / inputs ───────────────────────────────────── */
    .stTextArea textarea, .stTextInput input {
        background: rgba(7, 12, 7, 0.6) !important;
        border-color: var(--accent-border) !important;
        color: var(--text) !important;
        border-radius: 8px !important;
    }
    /* ── Chat message styling ─────────────────────────────────── */
    div[data-testid="stChatMessage"] {
        background: var(--panel) !important;
        border: 1px solid var(--accent-border) !important;
        border-radius: 12px !important;
        margin-bottom: 8px;
    }

    /* ── Compact toast / success / warning / error ────────────── */
    div[data-testid="stAlert"] {
        border-radius: 10px !important;
        font-size: 0.85rem !important;
    }

    /* ── Code block styling ───────────────────────────────────── */
    pre {
        background: rgba(5, 8, 5, 0.7) !important;
        border: 1px solid var(--accent-border) !important;
        border-radius: 8px !important;
    }

    /* ── Radio / toggle styling ───────────────────────────────── */
    div[data-baseweb="radio"] label span {
        color: var(--text) !important;
    }

    /* ── Download button ──────────────────────────────────────── */
    .stDownloadButton > button {
        background: transparent !important;
        border: 1px solid var(--accent) !important;
        color: var(--accent) !important;
    }
    .stDownloadButton > button:hover {
        background: var(--accent-soft) !important;
    }

    /* ── Breadcrumb / page context bar ────────────────────────── */
    .page-context-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 16px;
        margin: 0 0 16px;
        border-radius: 10px;
        background: rgba(7, 12, 7, 0.45);
        border: 1px solid var(--accent-border);
        font-size: 0.8rem;
        color: var(--muted);
    }
    .page-context-bar .ctx-title {
        font-weight: 700;
        color: var(--accent);
        font-size: 0.9rem;
    }
    .page-context-bar .ctx-meta {
        opacity: 0.8;
    }

    /* ── Empty state styling ──────────────────────────────────── */
    .empty-state {
        text-align: center;
        padding: 40px 20px;
        color: var(--muted);
        opacity: 0.7;
    }
    .empty-state .empty-icon {
        font-size: 2.5rem;
        margin-bottom: 8px;
    }
    .empty-state .empty-text {
        font-size: 0.9rem;
    }

    /* ── Footer ───────────────────────────────────────────────── */
    .dashboard-footer {
        text-align: center;
        padding: 20px 0 8px;
        font-size: 0.7rem;
        color: var(--muted);
        opacity: 0.5;
        border-top: 1px solid var(--accent-border);
        margin-top: 40px;
    }

    /* ── Keyboard shortcut hint ───────────────────────────────── */
    .kbd {
        display: inline-block;
        padding: 1px 6px;
        border: 1px solid var(--accent-border);
        border-radius: 4px;
        font-size: 0.7rem;
        color: var(--muted);
        background: rgba(7, 12, 7, 0.5);
        font-family: monospace;
    }

    /* ── Sidebar navigation overhaul ──────────────────────────── */
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }
    .sidebar-nav {
        display: flex;
        flex-direction: column;
        gap: 2px;
        margin: 0 -8px 12px;
    }
    .sidebar-nav-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 9px 14px;
        border-radius: 8px;
        font-size: 0.82rem;
        color: var(--muted);
        cursor: default;
        transition: all 120ms ease;
        border: 1px solid transparent;
    }
    .sidebar-nav-item:hover {
        background: var(--accent-soft);
        color: var(--accent);
        border-color: var(--accent-border);
    }
    .sidebar-nav-item .nav-icon {
        font-size: 1rem;
        width: 22px;
        text-align: center;
        flex-shrink: 0;
    }
    .sidebar-nav-item .nav-label {
        font-weight: 500;
    }
    .sidebar-nav-item .nav-badge {
        margin-left: auto;
        background: var(--accent-soft);
        border: 1px solid var(--accent-border);
        color: var(--accent);
        font-size: 0.68rem;
        font-weight: 700;
        padding: 1px 7px;
        border-radius: 10px;
        line-height: 1.4;
    }

    /* ── Sidebar compact status card ──────────────────────────── */
    .sb-status-card {
        border: 1px solid var(--accent-border);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 14px;
        background: rgba(7, 12, 7, 0.5);
        backdrop-filter: blur(6px);
    }
    .sb-status-row {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.82rem;
        padding: 3px 0;
    }
    .sb-status-row .sb-icon {
        width: 18px;
        text-align: center;
        flex-shrink: 0;
    }
    .sb-status-row .sb-label {
        color: var(--muted);
        min-width: 52px;
    }
    .sb-status-row .sb-value {
        color: var(--text);
        font-weight: 600;
    }
    .sb-status-row .sb-value.ok { color: var(--accent); }
    .sb-status-row .sb-value.warn { color: var(--warn); }
    .sb-status-row .sb-value.error { color: var(--danger); }
    .sb-status-row .sb-value.neutral { color: var(--muted); }

    .sb-divider {
        border: none;
        border-top: 1px solid var(--accent-border);
        margin: 10px 0;
    }

    .sb-section-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        opacity: 0.6;
        margin: 14px 0 6px;
        padding-left: 2px;
    }

    /* ── Sidebar action buttons ───────────────────────────────── */
    section[data-testid="stSidebar"] .stButton > button {
        font-size: 0.8rem;
        padding: 6px 12px;
        border-radius: 8px;
        width: 100%;
        justify-content: flex-start;
        gap: 8px;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: var(--accent-soft);
        transform: translateX(2px);
    }
    section[data-testid="stSidebar"] .sb-link-btn {
        display: block;
        width: 100%;
        text-align: left;
        font-size: 0.8rem;
        padding: 6px 12px;
        border-radius: 8px;
        color: var(--text);
        background: rgba(7, 12, 7, 0.4);
        border: 1px solid var(--accent-border);
        text-decoration: none;
        font-weight: 600;
        transition: all 0.2s ease;
        box-sizing: border-box;
    }

    /* ── Inbox: editor + preview overhaul ─────────────────────── */
    .inbox-shell{
        display:flex; flex-direction:column; gap:10px;
        padding: 14px 16px;
        border-radius: 14px;
        background: var(--panel);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(10px);
        box-shadow: 0 6px 28px rgba(0,0,0,0.35);
    }
    .inbox-shell .hint{
        font-size:0.78rem; color:var(--muted); opacity:0.8; line-height:1.5;
    }
    .inbox-help-card{
        padding: 14px 16px;
        border-radius: 14px;
        background: rgba(7, 12, 7, 0.40);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(8px);
    }
    .inbox-help-card h4{
        margin:0 0 8px;
        font-size:0.9rem;
        color: var(--accent);
        letter-spacing:0.02em;
    }
    .pill{
        display:inline-flex; align-items:center; gap:8px;
        padding:5px 10px;
        border-radius: 999px;
        border: 1px solid var(--accent-border);
        background: rgba(7, 12, 7, 0.45);
        color: var(--muted);
        font-size: 0.74rem;
        white-space: nowrap;
    }
    .pill strong{color:var(--text); font-weight:700;}
    .pill.urgent{border-color: rgba(255,68,68,0.35); color: rgba(255,170,170,0.95);}
    .pill.urgent strong{color: var(--danger);}
    .inbox-preview{
        border:1px solid var(--accent-border);
        border-radius: 14px;
        background: rgba(7, 12, 7, 0.35);
        padding: 10px 12px;
        max-height: 420px;
        overflow: auto;
    }
    .inbox-line{
        display:flex; gap:10px; align-items:flex-start;
        padding: 7px 6px;
        border-radius: 10px;
        transition: background 120ms ease, border-color 120ms ease;
        border:1px solid transparent;
    }
    .inbox-line:hover{
        background: rgba(57,255,20,0.06);
        border-color: var(--accent-border);
    }
    .inbox-dot{margin-top:3px; width:10px; height:10px; border-radius:50%; background: var(--accent); box-shadow: 0 0 10px rgba(57,255,20,0.25); flex-shrink:0;}
    .inbox-dot.urgent{background: var(--danger); box-shadow: 0 0 10px rgba(255,68,68,0.25);}
    .inbox-text{font-size:0.82rem; color:var(--text); line-height:1.45; word-break:break-word;}
    .inbox-empty{padding: 26px 10px; text-align:center; color:var(--muted); opacity:0.75; font-size:0.85rem;}

    section[data-testid="stSidebar"] .sb-link-btn:hover {
        background: var(--accent-soft);
        border-color: var(--accent);
        transform: translateX(2px);
    }

    /* ── Inbox editor polish ──────────────────────────────────── */
    .inbox-toolbar {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0 0 12px;
        flex-wrap: wrap;
    }
    .inbox-toolbar .inbox-stat {
        font-size: 0.78rem;
        color: var(--muted);
        padding: 4px 12px;
        border: 1px solid var(--accent-border);
        border-radius: 8px;
        background: rgba(7, 12, 7, 0.4);
    }
    .inbox-toolbar .inbox-stat strong {
        color: var(--accent);
        font-weight: 700;
    }

    /* ── Settings section cards ───────────────────────────────── */
    .settings-section {
        padding: 18px 20px;
        border-radius: 14px;
        background: var(--panel);
        border: 1px solid var(--accent-border);
        backdrop-filter: blur(10px);
        margin-bottom: 16px;
    }
    .settings-section h4 {
        margin: 0 0 10px;
        font-size: 0.95rem;
        color: var(--accent);
    }

    /* ── Inline key-value rows ────────────────────────────────── */
    .kv-grid {
        display: grid;
        grid-template-columns: auto 1fr;
        gap: 4px 16px;
        font-size: 0.82rem;
        margin: 6px 0 10px;
    }
    .kv-grid .kv-key {
        color: var(--muted);
        white-space: nowrap;
    }
    .kv-grid .kv-val {
        color: var(--text);
        font-weight: 600;
    }
    .kv-grid .kv-val.ok { color: var(--accent); }
    .kv-grid .kv-val.warn { color: var(--warn); }
    .kv-grid .kv-val.error { color: var(--danger); }

    /* ── Compact action bar ───────────────────────────────────── */
    .action-bar {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin: 12px 0;
    }

    /* ── Toast-style feedback ─────────────────────────────────── */
    .feedback-toast {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
        animation: fadeInUp 300ms ease;
    }
    .feedback-toast.success {
        background: rgba(57, 255, 20, 0.12);
        border: 1px solid rgba(57, 255, 20, 0.35);
        color: var(--accent);
    }
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(6px); }
        to { opacity: 1; transform: translateY(0); }
    }
    section[data-testid="stSidebar"] .sb-link-btn:hover {
        background: var(--accent-soft);
        border-color: var(--accent);
        transform: translateX(2px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def _page_context(title: str, description: str = "", extra_html: str = "") -> None:
    """Render a consistent page context bar at the top of each tab."""
    meta = f'<span class="ctx-meta">{description}</span>' if description else ""
    extra = f'<span class="ctx-meta">{extra_html}</span>' if extra_html else ""
    st.markdown(
        f'<div class="page-context-bar">'
        f'<span class="ctx-title">{title}</span>'
        f'{meta}{extra}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _latest_file(files: Iterable[Path]) -> Path | None:
    latest: Path | None = None
    latest_ts: datetime | None = None
    for p in files:
        dt = extract_timestamp(p)
        if not latest_ts or dt > latest_ts:
            latest = p
            latest_ts = dt
    return latest

def _fmt_time(value: str | datetime | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(PST).strftime("%b %d, %H:%M")
    if isinstance(value, str) and value.strip():
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(PST).strftime("%b %d, %H:%M")
        except Exception:
            return s[:16]
    return "—"

def _fmt_mtime(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).astimezone(PST).strftime("%b %d, %H:%M")
    except Exception:
        return "—"

def _read_cycle_health() -> tuple[str, str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists():
        return "unknown", "no cycle log found"
    last_status = "unknown"
    last_reason = ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-200:]):
            if "\"event\": \"autopatch\"" in line:
                if "\"returncode\": 0" in line:
                    last_status = "ok"
                    last_reason = "last autopatch succeeded"
                else:
                    last_status = "error"
                    last_reason = "last autopatch failed"
                break
        if last_status == "unknown":
            last_reason = "no autopatch event yet"
    except Exception:
        last_status = "unknown"
        last_reason = "failed to parse cycle log"
    return last_status, last_reason

def _last_autopatch_success_ts() -> datetime | None:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"autopatch\"" in line and "\"returncode\": 0" in line:
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts")
                    if ts:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    continue
    except Exception:
        return None
    return None

def _latest_routing() -> dict:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists():
        return {}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"routing\"" in line:
                try:
                    return json.loads(line)
                except Exception:
                    continue
    except Exception:
        return {}
    return {}

def _routing_config() -> dict:
    cfg_path = Path("/home/hackerman/agent-runtime/constitution/agent_routing.json")
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _openclaw_models() -> tuple[list[str], str]:
    cfg_path = Path("/home/hackerman/.openclaw/openclaw.json")
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    providers = cfg.get("models", {}).get("providers", {})
    local = providers.get("local-llama", {})
    models = [m.get("id") for m in local.get("models", []) if isinstance(m, dict) and m.get("id")]
    primary = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
    default = primary.split("/", 1)[-1] if primary else (models[0] if models else "llama-3.1-8b-instruct")
    if default not in models:
        models = [default] + [m for m in models if m != default]
    return models, default

def _active_provider_model() -> tuple[str, str]:
    cfg = _routing_config()
    routing = _latest_routing()
    provider = (routing.get("provider") or cfg.get("force_provider") or cfg.get("default_provider") or "unknown").strip().lower()
    model = "—"
    if provider == "codex":
        model = str(cfg.get("codex_model", "gpt-5.2-codex"))
    elif provider == "claude":
        model = str(cfg.get("claude_model", "claude-opus-4-6"))
    elif provider == "openai":
        model = str(cfg.get("openai_model", "gpt-5.2"))
    return provider, model

def _credit_snapshot() -> tuple[str, str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/autopatch_events.jsonl")
    if not log_path.exists():
        return "unknown", "No credit signal found."
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        last_credit_ts = None
        for line in reversed(lines[-400:]):
            if "\"event\": \"model_call\"" in line and "\"status\": \"error\"" in line:
                try:
                    obj = json.loads(line)
                    detail = (obj.get("detail") or "").lower()
                    ts = obj.get("ts")
                except Exception:
                    detail = line.lower()
                    ts = None
                if "credit" in detail or "billing" in detail or "quota" in detail:
                    if ts:
                        try:
                            last_credit_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except Exception:
                            last_credit_ts = None
                    if last_credit_ts:
                        break
        last_ok = _last_autopatch_success_ts()
        if last_credit_ts and last_ok and last_ok > last_credit_ts:
            return "ok", "No recent billing issues."
        if last_credit_ts:
            return "low", "Billing/credit issue detected recently."
        return "unknown", "No billing issues detected."
    except Exception:
        return "unknown", "Unable to parse credit log."

def _read_project_status() -> tuple[str, str]:
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    if not status_path.exists():
        return "UNKNOWN", "status file missing"
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        return data.get("status", "UNKNOWN"), data.get("timestamp", "")
    except Exception:
        return "UNKNOWN", "failed to parse status file"

def _cycle_label(health: str, project_status: str) -> tuple[str, str]:
    if health == "error" and project_status == "IN_PROGRESS":
        return "warn", "recent failure (work resumed)"
    return health, ""

def _last_cycle_ts() -> datetime | None:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"cycle_start\"" in line or "\"event\": \"autopatch\"" in line:
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts")
                    if ts:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    continue
    except Exception:
        return None
    return None

def _touch_trigger(note: str) -> None:
    trigger_path = Path("/home/hackerman/agent-runtime/directives/priorities/.trigger")
    try:
        ts = datetime.now(timezone.utc).isoformat()
        with trigger_path.open("a", encoding="utf-8") as f:
            f.write(f"{note} {ts}\n")
    except Exception:
        pass

def _inbox_is_urgent(line: str) -> bool:
    s = (line or "").strip().lower()
    if not s:
        return False
    # Common urgency patterns: leading tokens, markers, and high-signal words
    if s.startswith(("urgent:", "critical:", "blocker:", "asap:", "hotfix:")):
        return True
    if "!!!" in s:
        return True
    return any(kw in s for kw in (" urgent", " critical", " blocker", " asap", "sev1", "sev-1"))

def _render_sidebar() -> None:
    with st.sidebar:
        # ── Branding ─────────────────────────────────────────────
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=48)
        st.markdown(
            '<div style="font-size:0.95rem; font-weight:700; color:var(--accent); margin:-4px 0 2px;">Agent Runtime</div>'
            '<div style="font-size:0.65rem; color:var(--muted); opacity:0.6; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:8px;">Control Center</div>',
            unsafe_allow_html=True,
        )

        # ── Compact status card ──────────────────────────────────
        _sb_status, _sb_status_ts = _read_project_status()
        _sb_health, _sb_health_reason = _read_cycle_health()
        _sb_health_label, _sb_health_note = _cycle_label(_sb_health, _sb_status)
        _sb_health_variant = "ok" if _sb_health_label == "ok" else ("warn" if _sb_health_label == "warn" else ("error" if _sb_health_label == "error" else "neutral"))
        _sb_status_variant = "ok" if _sb_status == "IN_PROGRESS" else ("warn" if _sb_status == "PENDING_HUMAN_REVIEW" else ("ok" if _sb_status == "DONE" else "neutral"))
        _sb_provider, _sb_model = _active_provider_model()
        _sb_last_cycle = _last_cycle_ts()
        _sb_cycle_str = "—"
        if _sb_last_cycle:
            _sb_age = (datetime.now(timezone.utc) - _sb_last_cycle).total_seconds() / 60.0
            _sb_cycle_str = f"{_sb_age:.0f}m ago" if _sb_age < 60 else f"{_sb_age/60:.1f}h ago"

        _sb_all_files = list_matching(output_patterns())
        _sb_inbox_raw = read_inbox()
        _sb_inbox_lines = len([l for l in _sb_inbox_raw.splitlines() if l.strip()])

        st.markdown(
            f"""
            <div class="sb-status-card">
                <div class="sb-status-row">
                    <span class="sb-icon">●</span>
                    <span class="sb-label">Cycle</span>
                    <span class="sb-value {_sb_health_variant}">{_sb_health_label.upper()}</span>
                </div>
                <div class="sb-status-row">
                    <span class="sb-icon">◉</span>
                    <span class="sb-label">Project</span>
                    <span class="sb-value {_sb_status_variant}">{_sb_status}</span>
                </div>
                <div class="sb-status-row">
                    <span class="sb-icon">⏱</span>
                    <span class="sb-label">Last</span>
                    <span class="sb-value neutral">{_sb_cycle_str}</span>
                </div>
                <div class="sb-status-row">
                    <span class="sb-icon">⚡</span>
                    <span class="sb-label">Provider</span>
                    <span class="sb-value neutral">{_sb_provider.upper() if _sb_provider else '?'}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Quick actions ────────────────────────────────────────
        st.markdown('<div class="sb-section-label">Quick Actions</div>', unsafe_allow_html=True)
        if st.button("🔄  Refresh", key="sidebar_refresh", use_container_width=True):
            st.rerun()
        if st.button("📋  Brief me", key="sidebar_brief", use_container_width=True):
            st.session_state["_jump_to_brief"] = True
            st.rerun()
        if st.button("💬  Chat", key="sidebar_chat", use_container_width=True):
            st.session_state["_jump_to_chat"] = True
            st.rerun()
        llama_url = "http://127.0.0.1:11434"
        if hasattr(st, "link_button"):
            st.link_button("🦙  Open Llama", llama_url, use_container_width=True)
        else:
            st.markdown(
                f'<a class="sb-link-btn" href="{llama_url}" target="_blank" rel="noopener">🦙  Open Llama</a>',
                unsafe_allow_html=True,
            )
        if st.button("📝  Notes", key="sidebar_notes", use_container_width=True):
            st.session_state["_jump_to_notes"] = True
            st.rerun()
        if st.button("⚡  Kick cycle", key="sidebar_kick", use_container_width=True):
            _touch_trigger("sidebar_kick")
            st.success("Cycle triggered.")
            st.rerun()

        # ── Pinned note ─────────────────────────────────────────
        st.markdown('<div class="sb-section-label">📌 Pinned Note</div>', unsafe_allow_html=True)
        _pin_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/pinned_note.txt")
        _pin_text = ""
        if _pin_path.exists():
            try:
                _pin_text = _pin_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                pass
        if _pin_text:
            st.markdown(
                f'<div style="border:1px solid var(--accent-border); border-radius:8px; padding:8px 10px; '
                f'background:rgba(7,12,7,0.4); font-size:0.78rem; color:var(--text); white-space:pre-wrap; line-height:1.5;">'
                f'{_html.escape(_pin_text[:200])}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No pinned note yet.")

        # ── Stats ────────────────────────────────────────────────
        st.markdown('<div class="sb-section-label">Stats</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:8px;">
                <div style="text-align:center; padding:8px 4px; border-radius:8px; background:rgba(7,12,7,0.4); border:1px solid var(--accent-border);">
                    <div style="font-size:1.1rem; font-weight:700; color:var(--accent);">{len(_sb_all_files)}</div>
                    <div style="font-size:0.65rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em;">Proposals</div>
                </div>
                <div style="text-align:center; padding:8px 4px; border-radius:8px; background:rgba(7,12,7,0.4); border:1px solid var(--accent-border);">
                    <div style="font-size:1.1rem; font-weight:700; color:var(--accent);">{_sb_inbox_lines}</div>
                    <div style="font-size:0.65rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em;">Inbox</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Auto-refresh toggle ──────────────────────────────────
        st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
        auto_refresh = st.toggle("Auto-refresh (30s)", value=False, key="auto_refresh")
        if auto_refresh:
            st.caption("⟳ Refreshing every 30s")

        # ── Timestamp ────────────────────────────────────────────
        st.markdown(
            f'<div style="font-size:0.65rem; color:var(--muted); opacity:0.4; margin-top:12px; text-align:center;">'
            f'{datetime.now(PST).strftime("%H:%M PST")}</div>',
            unsafe_allow_html=True,
        )

def _latest_patch_name() -> str:
    logs = Path("/home/hackerman/agent-runtime/logs")
    if not logs.exists():
        return "—"
    items = sorted(logs.glob("dashboard_patch_*.diff"), key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0].name if items else "—"

def _recent_updates_global(max_lines: int = 8) -> list[dict]:
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if not projects_root.exists():
        return []
    items = []
    for p in projects_root.iterdir():
        if not p.is_dir():
            continue
        changelog = p / "CHANGELOG.md"
        if changelog.exists():
            try:
                lines = changelog.read_text(encoding="utf-8", errors="ignore").splitlines()
                lines = [ln for ln in lines if ln.strip()][:max_lines]
                if lines:
                    items.append({
                        "project": p.name,
                        "mtime": changelog.stat().st_mtime,
                        "lines": lines,
                    })
            except Exception:
                continue
    return sorted(items, key=lambda x: x["mtime"], reverse=True)

@st.dialog("Confirm: mark DONE")
def _confirm_done():
    st.write("This will mark the project as DONE and stop further cycles.")
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    c1, c2 = st.columns(2)
    if c1.button("Yes, mark DONE"):
        status_path.write_text(
            json.dumps({"status": "DONE", "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2),
            encoding="utf-8",
        )
        st.success("Marked DONE")
        st.rerun()
    if c2.button("Cancel"):
        st.info("Cancelled")
        st.rerun()

@st.dialog("Confirm: continue work")
def _confirm_continue():
    st.write("This will resume cycles and mark status IN_PROGRESS.")
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    c1, c2 = st.columns(2)
    if c1.button("Yes, continue"):
        status_path.write_text(
            json.dumps({"status": "IN_PROGRESS", "timestamp": datetime.now(timezone.utc).isoformat(), "reason": "needs more work"}, indent=2),
            encoding="utf-8",
        )
        _write_continue_work_override("agent-dashboard", Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard"))
        _touch_trigger("continue_work")
        st.warning("Set to IN_PROGRESS")
        st.rerun()
    if c2.button("Cancel"):
        st.info("Cancelled")
        st.rerun()

def _write_continue_work_override(project: str, project_path: Path) -> Path:
    overrides_dir = Path("/home/hackerman/agent-runtime/directives/overrides")
    overrides_dir.mkdir(parents=True, exist_ok=True)
    override_path = overrides_dir / f"continue_work_{project}.md"
    override_path.write_text(
        "# Continue Work\n"
        f"Project: {project}\n"
        f"Path: {project_path}\n\n"
        "Generate a new improvement proposal based on the latest project state. "
        "Study WORK_ORDER.md and current code, identify gaps vs the existing Definition of Done, "
        "and propose the next iteration with clear steps and updated Definition of Done.\n",
        encoding="utf-8",
    )
    return override_path

def _recent_failures(limit: int = 3) -> list[str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists():
        return []
    failures: list[str] = []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"autopatch\"" in line and "\"returncode\": 0" not in line:
                failures.append(line)
            if len(failures) >= limit:
                break
    except Exception:
        return []
    return failures

def _dismissed_errors_path() -> Path:
    return Path("/home/hackerman/agent-runtime/logs/dismissed_errors.json")

def _load_dismissed_errors() -> set[str]:
    path = _dismissed_errors_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception:
        return set()
    return set()

def _save_dismissed_errors(ids: set[str]) -> None:
    path = _dismissed_errors_path()
    try:
        path.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
    except Exception:
        pass

def _error_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]

def _copy_button(text: str, key: str) -> None:
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    badge_id = f"copy_badge_{key}"
    btn_id = f"copy_btn_{key}"
    html = f"""
    <style>
    html, body {{ margin:0; padding:0; background:transparent; }}
    * {{ box-sizing: border-box; }}
    .copy-btn {{
        background:transparent;
        border:1px solid #39ff14;
        color:#39ff14;
        padding:6px 10px;
        border-radius:8px;
        cursor:pointer;
        box-shadow:0 0 12px rgba(57,255,20,0.6);
        transition: all 120ms ease;
        font-weight:600;
    }}
    .copy-btn:active {{
        transform: scale(0.96);
        box-shadow:0 0 20px rgba(57,255,20,0.9);
    }}
    .copy-btn.copied {{
        color:#0b0f0b;
        background:#39ff14;
        box-shadow:0 0 20px rgba(57,255,20,0.9);
    }}
    .copy-badge {{
        margin-left:8px;
        font-size:0.7rem;
        color:#39ff14;
        opacity:0;
        transition: opacity 120ms ease;
    }}
    </style>
    <div style="display:flex; align-items:center; gap:6px;">
      <button id="{btn_id}" class="copy-btn" title="Copy to clipboard"
        onclick="
          const btn=this;
          const badge=document.getElementById('{badge_id}');
          navigator.clipboard.writeText(`{safe}`).then(()=>{{
            btn.classList.add('copied');
            btn.innerText='COPIED';
            badge.innerText='Copied';
            badge.style.opacity=1;
            setTimeout(()=>{{btn.classList.remove('copied'); btn.innerText='⧉'; badge.style.opacity=0;}}, 1100);
          }}).catch(()=>{{
            badge.innerText='Blocked';
            badge.style.opacity=1;
            setTimeout(()=>{{badge.style.opacity=0;}}, 1500);
          }});
        ">⧉</button>
      <span id="{badge_id}" class="copy-badge">Copied</span>
    </div>
    """
    components.html(html, height=34, width=120)

def _failure_row(text: str, key: str) -> None:
    safe = _html.escape(text)
    badge_id = f"err_badge_{key}"
    html = f"""
    <style>
    html, body {{ margin:0; padding:0; background:transparent; }}
    * {{ box-sizing: border-box; }}
    .row {{ display:flex; gap:12px; align-items:flex-start; }}
    .card {{
        flex:1;
        border:1px solid rgba(57,255,20,0.25);
        background:rgba(0,0,0,0.35);
        border-radius:12px;
        padding:10px 12px;
        box-shadow:0 4px 16px rgba(0,0,0,0.35);
    }}
    .copy {{
        min-width:34px; height:34px; display:flex; align-items:center; justify-content:center;
        border:1px solid #39ff14; color:#39ff14; border-radius:8px; cursor:pointer;
        box-shadow:0 0 12px rgba(57,255,20,0.6); background:transparent;
        font-weight:600;
    }}
    .copy.copied {{
        color:#0b0f0b;
        background:#39ff14;
        box-shadow:0 0 20px rgba(57,255,20,0.9);
    }}
    .copy-badge {{
        margin-top:6px;
        font-size:0.7rem;
        color:#39ff14;
        opacity:0;
        transition: opacity 120ms ease;
    }}
    pre {{
        margin:0;
        background:transparent;
        color:#eaffea; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        white-space:pre-wrap; word-break:break-word; max-height:72px; overflow:hidden;
    }}
    </style>
    <div class="row">
        <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
          <button class="copy" onclick="
            const btn=this;
            const badge=document.getElementById('{badge_id}');
            navigator.clipboard.writeText(`{safe}`).then(()=>{{
              btn.classList.add('copied'); btn.innerText='COPIED';
              badge.innerText='Copied'; badge.style.opacity=1;
              setTimeout(()=>{{btn.classList.remove('copied'); btn.innerText='⧉'; badge.style.opacity=0;}}, 1100);
            }}).catch(()=>{{
              badge.innerText='Blocked'; badge.style.opacity=1;
              setTimeout(()=>{{badge.style.opacity=0;}}, 1500);
            }});
          ">⧉</button>
          <span id="{badge_id}" class="copy-badge">Copied</span>
        </div>
        <div class="card"><pre>{safe}</pre></div>
    </div>
    """
    components.html(html, height=90)

def _summarize_event(evt: dict) -> str:
    event = evt.get("event", "")
    if event == "proposal_ok":
        pid = evt.get("proposal_id", "unknown")
        planner = evt.get("planner", "claude").capitalize()
        return f"{planner} drafted a proposal ({pid})."
    if event == "review_written":
        critic = evt.get("critic", "codex").capitalize()
        return f"{critic} reviewed the proposal."
    if event == "proposal_skipped":
        return "No new projects; proposal step skipped."
    if event == "executor_run":
        code = evt.get("returncode")
        if code == 0:
            return f"Executor applied a patch and ran checks ({_latest_patch_name()})."
        return "Executor failed during patch/checks."
    if event == "autopatch":
        code = evt.get("returncode")
        return "Autopatch succeeded (diff generated)." if code == 0 else "Autopatch failed to produce a valid diff."
    if event == "check":
        name = evt.get("name", "check")
        return f"Validation check: {name} {'passed' if evt.get('passed') else 'failed'}."
    if event == "done":
        return "Marked ready for review (all gates satisfied)."
    if event == "in_progress":
        return "Cycle completed; continuing work (more improvements needed)."
    if event == "routing":
        provider = evt.get("provider", "unknown")
        return f"Routed this cycle to {provider.upper()} for the next patch."
    return "Activity updated."


def _parse_event_lines(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-limit:]):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if "event" in obj:
                items.append(obj)
    except Exception:
        return []
    return items


def _agent_activity() -> tuple[str, str]:
    router_path = Path("/home/hackerman/agent-runtime/logs/router_events.jsonl")
    cycle_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    router_items = _parse_event_lines(router_path, limit=200)
    cycle_items = _parse_event_lines(cycle_path, limit=400)
    items = router_items[:5] + cycle_items[:5]
    if not items:
        return "unknown", "no activity logs found"
    # Pick the most recent timestamp
    def _ts_dt(obj: dict) -> datetime | None:
        ts = obj.get("ts", "")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    items.sort(key=lambda obj: _ts_dt(obj) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    latest = items[0]
    summary = _summarize_event(latest)
    status = "active"

    if latest.get("event") in ("proposal_skipped",) or "no activity" in summary.lower():
        status = "idle"

    latest_dt = _ts_dt(latest)
    if latest_dt:
        age_min = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 60.0
        if age_min >= 60:
            status = "idle"
            hrs = int(age_min // 60)
            mins = int(age_min % 60)
            age_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
            summary = f"{summary} (last activity {age_str} ago)"

    return status, summary


def _activity_feed(limit: int = 6) -> list[dict]:
    router_path = Path("/home/hackerman/agent-runtime/logs/router_events.jsonl")
    cycle_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    items = _parse_event_lines(router_path, limit=200) + _parse_event_lines(cycle_path, limit=400)
    if not items:
        return []
    def _ts(obj: dict) -> str:
        return obj.get("ts", "")
    items.sort(key=_ts, reverse=True)
    out = []
    for obj in items[:limit]:
        ts = obj.get("ts", "")
        out.append({
            "ts": ts,
            "summary": _summarize_event(obj),
        })
    return out


def _chip(label: str, variant: str) -> str:
    return f'<span class="status-chip {variant}">{label}</span>'


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    for sep in (". ", ".\n", ".\t"):
        if sep in text:
            return text.split(sep, 1)[0].strip() + "."
    return text.strip()


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value:
        return [str(value).strip()]
    return []


def _tech_notes(payload: dict) -> str:
    text = " ".join(
        [
            str(payload.get("summary") or ""),
            str(payload.get("context") or ""),
            str(payload.get("reasoning") or ""),
            " ".join(_as_list(payload.get("suggested_actions"))),
        ]
    ).lower()
    keywords = [
        "solana",
        "base",
        "evm",
        "supabase",
        "postgres",
        "postgresql",
        "next.js",
        "react",
        "tailwind",
        "streamlit",
        "wallet",
        "multisig",
        "safe",
        "squads",
        "intent",
        "policy",
        "approval",
        "api",
        "sdk",
        "dashboard",
        "agent",
        "automation",
        "workflow",
        "python",
    ]
    found = [k for k in keywords if k in text]
    return ", ".join(sorted(set(found))) if found else "—"


def _edge_from_text(payload: dict) -> str:
    text = " ".join(
        [
            str(payload.get("summary") or ""),
            str(payload.get("context") or ""),
            str(payload.get("reasoning") or ""),
        ]
    ).lower()
    if "approval" in text or "policy" in text or "audit" in text:
        return "Safety-first approvals and audit trail."
    if "speed" in text or "fast" in text:
        return "Speed to execution with clear guardrails."
    if "accuracy" in text:
        return "Trustworthy reporting and visibility."
    return "Clear scope + rapid iteration."


def _investor_synopsis(payload: dict) -> dict[str, str]:
    summary = str(payload.get("summary") or "").strip()
    context = str(payload.get("context") or "").strip()
    reasoning = str(payload.get("reasoning") or "").strip()
    actions = _as_list(payload.get("suggested_actions"))
    return {
        "what": summary or _first_sentence(context),
        "why": _first_sentence(reasoning) or _first_sentence(context),
        "edge": _edge_from_text(payload),
        "next": actions[0] if actions else "Review proposal details.",
        "tech": _tech_notes(payload),
    }


def _http_probe(url: str, expect_json_status: bool = False, timeout: int = 2) -> tuple[str, str]:
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            status = r.status
            body = r.read(2000).decode("utf-8", "ignore")
        if 200 <= status < 400:
            if expect_json_status:
                try:
                    data = _json.loads(body)
                    st_val = str(data.get("status") or data.get("state") or "").lower()
                    if st_val in ("ok", "healthy", "ready", "running"):
                        return "ok", f"HTTP {status} · {st_val}"
                    if st_val:
                        return "warn", f"HTTP {status} · {st_val}"
                except Exception:
                    pass
            return "ok", f"HTTP {status}"
        return "error", f"HTTP {status}"
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"

# ── Header (rendered after helpers are defined) ──────────────────
cols_title = st.columns([1, 8])
with cols_title[0]:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=72)
with cols_title[1]:
    # Compute uptime string for header
    _hdr_last_cycle = _last_cycle_ts()
    _hdr_uptime = ""
    if _hdr_last_cycle:
        _hdr_age_min = (datetime.now(timezone.utc) - _hdr_last_cycle).total_seconds() / 60.0
        _hdr_uptime = f"{_hdr_age_min:.0f}m ago" if _hdr_age_min < 60 else f"{_hdr_age_min/60:.1f}h ago"
    _hdr_health, _ = _read_cycle_health()
    _hdr_health_color = "var(--accent)" if _hdr_health == "ok" else ("var(--warn)" if _hdr_health in ("warn", "unknown") else "var(--danger)")
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
            <h1 style="margin:0; padding:0; font-size:1.8rem; letter-spacing:-0.02em;">
                Agent Runtime Dashboard
            </h1>
            <span class="pulse" style="margin-top:4px;"></span>
        </div>
        <div style="font-size:0.78rem; color:var(--muted); margin-top:-2px; letter-spacing:0.04em;">
            AUTONOMOUS ENGINEERING CONTROL CENTER
            <span style="margin-left:16px; color:{_hdr_health_color}; font-weight:600;">● {_hdr_health.upper()}</span>
            {f'<span style="margin-left:8px; opacity:0.7;">Last cycle: {_hdr_uptime}</span>' if _hdr_uptime else ''}
        </div>
        <div style="font-size:0.68rem; color:var(--muted); margin-top:2px; opacity:0.5;">
            {datetime.now(PST).strftime("%A, %B %d · %H:%M PST")}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Small spacer before tabs
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

tabs = st.tabs([
    "🏠 Overview", "📁 Projects", "📥 Inbox", "📄 Outputs",
    "📈 Timeline", "⚙️ Settings", "💬 Chat", "📋 Logs",
    "❤️ Health", "📰 Digest", "📝 Notes",
])

_render_sidebar()

with tabs[0]:
    _page_context(
        "System Overview",
        "Real-time status snapshot of the agent runtime.",
        f"Updated {datetime.now(PST).strftime('%H:%M PST')}",
    )
    st.markdown('<div class="section-header">📊 Status Snapshot</div>', unsafe_allow_html=True)

    _ov_all_files = list_matching(output_patterns())
    _ov_latest_any = _latest_file(_ov_all_files)
    _ov_latest_review_file = _latest_file([p for p in _ov_all_files if p.name.startswith("review_")])
    inbox_raw = read_inbox()
    _ov_inbox_count = len([l for l in inbox_raw.splitlines() if l.strip()])

    # System health data
    _ov_health, _ov_reason = _read_cycle_health()
    _ov_ps, _ = _read_project_status()
    _ov_health_label, _ov_health_note = _cycle_label(_ov_health, _ov_ps)
    _ov_provider, _ov_model = _active_provider_model()
    _ov_credit_status, _ov_credit_note = _credit_snapshot()
    _ov_last_cycle = _last_cycle_ts()

    # Status chips
    _ov_health_variant = "ok" if _ov_health_label == "ok" else ("warn" if _ov_health_label == "warn" else ("error" if _ov_health_label == "error" else "neutral"))
    _ov_credit_variant = "ok" if _ov_credit_status == "ok" else ("warn" if _ov_credit_status == "low" else "neutral")
    _ov_status_variant = "ok" if _ov_ps == "IN_PROGRESS" else ("warn" if _ov_ps == "PENDING_HUMAN_REVIEW" else ("ok" if _ov_ps == "DONE" else "neutral"))

    # Hero stat grid (HTML for tighter layout)
    _ov_latest_activity_str = _fmt_time(stat_mtime_iso(_ov_latest_any)) if _ov_latest_any else "—"
    _ov_latest_review_str = _fmt_time(stat_mtime_iso(_ov_latest_review_file)) if _ov_latest_review_file else "—"
    _ov_cycle_age_str = "—"
    if _ov_last_cycle:
        _ov_age_min = (datetime.now(timezone.utc) - _ov_last_cycle).total_seconds() / 60.0
        _ov_cycle_age_str = f"{_ov_age_min:.0f}m" if _ov_age_min < 60 else f"{_ov_age_min/60:.1f}h"

    st.markdown(
        f"""
        <div class="hero-grid">
            <div class="hero-stat"><div class="value">{len(_ov_all_files)}</div><div class="label">Proposals</div></div>
            <div class="hero-stat"><div class="value">{_ov_inbox_count}</div><div class="label">Inbox Items</div></div>
            <div class="hero-stat"><div class="value">{_ov_latest_activity_str}</div><div class="label">Last Activity</div></div>
            <div class="hero-stat"><div class="value">{_ov_cycle_age_str}</div><div class="label">Cycle Age</div></div>
            <div class="hero-stat"><div class="value">{_ov_provider.upper() if _ov_provider else '?'}</div><div class="label">Provider</div></div>
            <div class="hero-stat"><div class="value">{_ov_latest_review_str}</div><div class="label">Last Review</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Status chips row
    st.markdown(
        f"""
        <div class="data-strip">
            {_chip('Cycle: ' + _ov_health_label.upper(), _ov_health_variant)}
            {_chip('Project: ' + _ov_ps, _ov_status_variant)}
            {_chip('Credits: ' + _ov_credit_status.upper(), _ov_credit_variant)}
            {_chip('Approval Gate: ' + ('ON' if approval_gate_enabled() else 'OFF'), 'ok' if approval_gate_enabled() else 'neutral')}
        </div>
        <div style="font-size:0.78rem; color:var(--muted); line-height:1.6; margin-bottom:12px;">
            🔧 {_ov_reason} · Patch: <code>{_latest_patch_name()}</code> · Model: <code>{_ov_model}</code>
            {(' · ' + _ov_health_note) if _ov_health_note else ''}<br>
            💳 {_ov_credit_note}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Latest proposal quick-approval
    st.markdown('<div class="section-header">🧾 Latest Proposal</div>', unsafe_allow_html=True)
    _ov_proposals = [p for p in _ov_all_files if not p.name.startswith("review_")]
    _ov_latest_proposal = _latest_file(_ov_proposals)
    if not _ov_latest_proposal:
        st.caption("No proposals available yet.")
    else:
        try:
            _ov_payload = read_json_file(_ov_latest_proposal)
        except Exception:
            _ov_payload = {}
        _ov_decision = read_decision(_ov_latest_proposal)
        _ov_summary = str(_ov_payload.get("summary") or "").strip()
        _ov_context = str(_ov_payload.get("context") or "").strip()
        _ov_overview = _ov_payload.get("overview")
        _ov_proj_summary = _ov_payload.get("project_summary")
        _ov_tech = _ov_payload.get("tech_details")
        _ov_done = _ov_payload.get("definition_of_done")
        _ov_project = str(_ov_payload.get("project") or "").strip()
        _ov_id = str(_ov_payload.get("proposal_id") or _ov_latest_proposal.stem)
        _ov_mode = str(_ov_payload.get("mode") or "—")
        _ov_time = _fmt_time(stat_mtime_iso(_ov_latest_proposal))

        _ov_synopsis = _investor_synopsis(_ov_payload)

        left, right = st.columns([1.4, 1], gap="large")
        with left:
            st.markdown(
                f"""
                <div class="glass-card">
                    <div class="card-title-row">
                        <div class="title">{_html.escape(_ov_summary) if _ov_summary else 'Latest proposal'}</div>
                        <div class="meta">{_html.escape(_ov_time)}</div>
                    </div>
                    <div class="glass-meta">ID: {_html.escape(_ov_id)} · Mode: {_html.escape(_ov_mode)} · Project: {_html.escape(_ov_project or '—')}</div>
                    <div class="subtle" style="margin-top:8px; white-space:pre-wrap;">{_html.escape(str(_ov_overview or _ov_context or '—'))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("**Investor-style synopsis**")
            st.markdown(
                "\n".join(
                    [
                        f"- **What it is:** {_ov_synopsis.get('what') or '—'}",
                        f"- **Why now:** {_ov_synopsis.get('why') or '—'}",
                        f"- **Edge:** {_ov_synopsis.get('edge') or '—'}",
                        f"- **Next step:** {_ov_synopsis.get('next') or '—'}",
                        f"- **Tech notes:** {_ov_synopsis.get('tech') or '—'}",
                    ]
                )
            )
            st.markdown("**Project summary**")
            st.caption(str(_ov_proj_summary or "—"))
            st.markdown("**Tech details**")
            st.caption(str(_ov_tech or "—"))
            st.markdown("**Definition of Done**")
            _ov_done_list = _as_list(_ov_done)
            if _ov_done_list:
                st.markdown("\n".join([f"- {item}" for item in _ov_done_list]))
            else:
                st.caption("—")
            if _ov_decision:
                st.caption(f"Decision: {_ov_decision.get('decision','—')} · {_ov_decision.get('timestamp','—')}")
        with right:
            _gate_on = approval_gate_enabled()
            _note = st.text_input(
                "Decision note (optional)",
                key=f"ov_note_{_ov_latest_proposal.name}",
                placeholder="Why approve or reject?",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Approve", key=f"ov_approve_{_ov_latest_proposal.name}"):
                    priority_path = write_priority_from_proposal(_ov_latest_proposal, _ov_payload, _note)
                    write_decision(
                        _ov_latest_proposal,
                        "APPROVE",
                        note=_note,
                        extra={"priority_path": str(priority_path)},
                    )
                    if _gate_on:
                        trigger_run()
                        st.success(f"Approved and queued. Priority saved to {priority_path}.")
                    else:
                        st.success(f"Approved. Draft priority saved to {priority_path}.")
                    st.rerun()
            with c2:
                if st.button("Reject", key=f"ov_reject_{_ov_latest_proposal.name}"):
                    write_decision(_ov_latest_proposal, "REJECT", note=_note)
                    st.warning("Rejected. Decision recorded.")
                    st.rerun()

            if (not _gate_on) and _ov_decision and _ov_decision.get("priority_path"):
                if st.button("Promote to active", key=f"ov_promote_{_ov_latest_proposal.name}"):
                    promoted = promote_priority(Path(_ov_decision["priority_path"]))
                    trigger_run()
                    st.success(f"Promoted to active priority: {promoted}")
                    st.rerun()

    # Two-column: Activity feed + Failures
    _ov_left, _ov_right = st.columns([1.2, 1], gap="large")

    with _ov_left:
        st.markdown('<div class="section-header" style="margin-top:0;">🤖 Activity Feed</div>', unsafe_allow_html=True)
        _ov_status, _ov_detail = _agent_activity()
        _ov_status_label = "CONNECTED" if _ov_status == "active" else ("IDLE" if _ov_status == "idle" else "UNKNOWN")
        _ov_accent = "var(--accent)" if _ov_status == "active" else "var(--muted)"
        _ov_pulse = '<span class="pulse"></span>' if _ov_status == "active" else ""

        st.markdown(
            f'<div style="font-size:0.85rem; margin-bottom:10px;">'
            f'{_ov_pulse}<span style="color:{_ov_accent};font-weight:700;">{_ov_status_label}</span>'
            f' — {_ov_detail}</div>',
            unsafe_allow_html=True,
        )

        feed = _activity_feed(limit=8)
        if feed:
            timeline_items = []
            for i, item in enumerate(feed):
                dot_class = "" if i == 0 else "dimmed"
                timeline_items.append(
                    f'<div class="activity-item">'
                    f'<div class="activity-dot {dot_class}"></div>'
                    f'<div class="activity-content">'
                    f'<div class="activity-ts">{_fmt_time(item["ts"])}</div>'
                    f'<div class="activity-text">{item["summary"]}</div>'
                    f'</div></div>'
                )
            st.markdown(
                f'<div class="activity-timeline">{"".join(timeline_items)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No recent activity found.")

    with _ov_right:
        st.markdown('<div class="section-header" style="margin-top:0;">⚠️ Recent Issues</div>', unsafe_allow_html=True)
        failures = _recent_failures(3)
        dismissed = _load_dismissed_errors()
        if failures:
            show_dismissed = st.toggle("Show dismissed", value=False, key="show_dismissed_errors")
            _any_shown = False
            for line in failures:
                err_id = _error_id(line)
                if (err_id in dismissed) and not show_dismissed:
                    continue
                _any_shown = True
                c_err, c_btn = st.columns([14, 3])
                with c_err:
                    _failure_row(line[:400], key=err_id)
                with c_btn:
                    label = "Dismiss" if err_id not in dismissed else "Restore"
                    if st.button(label, key=f"dismiss_{err_id}"):
                        if err_id in dismissed:
                            dismissed.remove(err_id)
                        else:
                            dismissed.add(err_id)
                        _save_dismissed_errors(dismissed)
                        st.rerun()
            if not _any_shown:
                st.success("All failures dismissed.")
        else:
            st.success("No recent issues — all systems nominal. ✓")

    st.divider()
    st.markdown('<div class="section-header">🎛️ Review & Cycle Control</div>', unsafe_allow_html=True)
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    current_status = "UNKNOWN"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            current_status = data.get("status", "UNKNOWN")
        except Exception:
            current_status = "UNKNOWN"
    ctrl_cols = st.columns(2, gap="large")
    with ctrl_cols[0]:
        st.markdown("**Review decision**")
        if current_status == "PENDING_HUMAN_REVIEW":
            st.warning("Review required: dashboard is waiting for your decision.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Approve (DONE)"):
                    _confirm_done()
            with c2:
                if st.button("Continue work"):
                    _confirm_continue()
        else:
            st.caption("No review actions needed right now.")

    with ctrl_cols[1]:
        st.markdown("**Cycle control**")
        last_cycle = _ov_last_cycle
        if last_cycle:
            age_min = (datetime.now(timezone.utc) - last_cycle).total_seconds() / 60.0
            if age_min >= 30:
                st.warning(f"Cycle looks idle. Last run: {_fmt_time(last_cycle.isoformat())}")
                if st.button("Kick cycle now"):
                    _touch_trigger("manual_kick")
                    st.success("Triggered a new cycle.")
                    st.rerun()
            else:
                st.caption(f"Last cycle: {_fmt_time(last_cycle.isoformat())}")
                if st.button("Force new cycle"):
                    _touch_trigger("manual_kick")
                    st.success("Triggered a new cycle.")
                    st.rerun()
        else:
            st.info("No cycle history yet.")
            if st.button("Kick cycle now"):
                _touch_trigger("manual_kick")
                st.success("Triggered a new cycle.")
                st.rerun()

    st.markdown('<div class="section-header">🧠 Brief Me</div>', unsafe_allow_html=True)
    st.caption("Summarize inbox and latest proposals with the local OpenClaw agent.")

    models, default_model = _openclaw_models()
    if models:
        st.caption(f"Model: {default_model}")
    else:
        st.warning("OpenClaw model not configured. Check ~/.openclaw/openclaw.json.")

    if models and st.button("Brief me"):
        inbox_text = inbox_raw.strip()
        cpath = latest_proposal_any()
        rpath = latest_review_any()

        def _json_blob(p: Path | None) -> str:
            if not p:
                return "(none)"
            try:
                data = read_json_file(p)
                return json.dumps(data, indent=2)[:12000]
            except Exception as e:
                return f"(failed to read {p.name}: {e})"

        prompt = (
            "You are a private agent assistant. Summarize the inbox and the latest proposals in ONE concise paragraph.\n"
            "Focus on: priorities, risks/blocks, and next actions.\n\n"
            "Be specific and actionable. Use bullet points for next actions.\n\n"
            "INBOX:\n"
            f"{inbox_text or '(empty)'}\n\n"
            "LATEST_CLAUDE_PROPOSAL_JSON:\n"
            f"{_json_blob(cpath)}\n\n"
            "LATEST_OPENAI_REVIEW_JSON:\n"
            f"{_json_blob(rpath)}\n"
            "\nEnd with a one-line status verdict: 🟢 All clear, 🟡 Needs attention, or 🔴 Action required."
        )
        with st.spinner("Generating briefing…"):
            try:
                out = generate(default_model, prompt, timeout=90)
                st.session_state["briefing_ts"] = datetime.now(PST).strftime("%b %d, %H:%M:%S")
                st.session_state["briefing"] = out
            except Exception as e:
                st.error(f"Briefing failed or timed out: {e}")

    if "briefing" in st.session_state:
        st.text_area("Briefing", value=st.session_state["briefing"], height=320)
        _copy_button(st.session_state["briefing"], key="copy_briefing")

        if "briefing_ts" in st.session_state:
            st.caption(f"Generated at {st.session_state['briefing_ts']}")
    st.markdown('<div class="section-header">📂 Project Overview</div>', unsafe_allow_html=True)
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    projects = []
    if projects_root.exists():
        projects = [p for p in projects_root.iterdir() if p.is_dir()]
    else:
        st.warning("Projects directory not found.")
        projects = []

    def _project_status(p: Path) -> tuple[str, str]:
        status_path = p / "status.json"
        if status_path.exists():
            try:
                data = json.loads(status_path.read_text(encoding="utf-8"))
                status = data.get("status", "UNKNOWN")
                ts = data.get("timestamp", "")
                return status, ts
            except Exception:
                return "UNKNOWN", ""
        return "UNKNOWN", ""

    def _preview_url(p: Path) -> str | None:
        candidates = [
            p / "dashboard.url",
            p / "preview.url",
            p / "assets" / "preview.url",
        ]
        for c in candidates:
            if c.exists():
                url = c.read_text(encoding="utf-8", errors="ignore").strip()
                if url.startswith("http://") or url.startswith("https://"):
                    return url
        return None

    if not projects:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">📂</div>'
            '<div class="empty-text">No projects found yet. Projects will appear here once the agent starts working.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        all_outputs = list_matching(output_patterns())

        def _latest_related_proposal(project_name: str) -> Path | None:
            hits: list[Path] = []
            needle = project_name.lower()
            for p in all_outputs:
                if p.name.startswith("review_"):
                    continue
                try:
                    data = read_json_file(p)
                except Exception:
                    data = {}
                text = f"{p.name} {data.get('proposal_id','')} {data.get('summary','')} {data.get('context','')}".lower()
                if needle in text:
                    hits.append(p)
            return _latest_file(hits) if hits else None

        def _thumb_data(p: Path) -> str | None:
            candidates = [
                p / "thumbnail.png",
                p / "thumbnail.jpg",
                p / "assets" / "thumbnail.png",
                p / "assets" / "preview.png",
            ]
            for c in candidates:
                if c.exists():
                    mime = "image/png" if c.suffix.lower() == ".png" else "image/jpeg"
                    data = base64.b64encode(c.read_bytes()).decode("ascii")
                    return f"data:{mime};base64,{data}"
            return None

        cards = []
        for p in sorted(projects, key=lambda x: x.stat().st_mtime, reverse=True)[:8]:
            status, ts = _project_status(p)
            last_mod = _fmt_mtime(p)
            thumb = _thumb_data(p)
            preview = _preview_url(p)
            latest_prop = _latest_related_proposal(p.name)
            latest_prop_label = latest_prop.name if latest_prop else "—"
            thumb_html = f'<img src="{thumb}" style="width:100%;border-radius:10px;margin:8px 0 10px;" />' if thumb else ""
            preview_html = f'<a href="{preview}" target="_blank" style="color:var(--accent);text-decoration:none;">Open Preview →</a>' if preview else ""
            cards.append(
                f"""
                <div class="glass-card">
                    <div class="glass-title">{p.name}</div>
                    <div class="glass-meta">Status: {status}</div>
                    <div class="glass-meta">Updated: {_fmt_time(ts) if ts else last_mod}</div>
                    <div class="glass-meta">Latest proposal: {latest_prop_label}</div>
                    {thumb_html}
                    {preview_html}
                </div>
                """
            )
        st.markdown(f"<div class=\"glass-grid\">{''.join(cards)}</div>", unsafe_allow_html=True)

        st.markdown("**Currently working on**")
        active = [p for p in projects if _project_status(p)[0] == "IN_PROGRESS"]
        if not active:
            st.caption("No active projects right now.")
        else:
            for p in active:
                status, ts = _project_status(p)
                st.markdown(f"- **{p.name}** · {status} · {_fmt_time(ts) if ts else 'recently updated'}")

        st.divider()
        st.markdown('<div class="section-header" style="font-size:0.95rem;">📡 Activity Feed</div>', unsafe_allow_html=True)
        updates = _recent_updates_global()
        if not updates:
            st.caption("No recent updates yet.")
        else:
            for item in updates[:5]:
                st.markdown(f"**{item['project']}**")
                st.code("\n".join(item["lines"]), language="text")

with tabs[1]:
    _page_context(
        "Projects",
        "All workspace projects with status and recent changes.",
    )

    _proj_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    _proj_list = []
    if _proj_root.exists():
        _proj_list = [p for p in _proj_root.iterdir() if p.is_dir()]

    def _read_lines_safe(path: Path, max_lines: int = 6) -> list[str]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return [ln for ln in lines if ln.strip()][:max_lines]
        except Exception:
            return []

    def _project_status_fn(p: Path) -> tuple[str, str]:
        status_path = p / "status.json"
        if status_path.exists():
            try:
                data = json.loads(status_path.read_text(encoding="utf-8"))
                return data.get("status", "UNKNOWN"), data.get("timestamp", "")
            except Exception:
                return "UNKNOWN", ""
        return "UNKNOWN", ""

    def _project_recent_changes(p: Path) -> list[str]:
        changelog = p / "CHANGELOG.md"
        if changelog.exists():
            return _read_lines_safe(changelog, 6)
        return []

    def _project_file_count(p: Path) -> int:
        try:
            return sum(1 for f in p.rglob("*") if f.is_file() and not f.name.startswith("."))
        except Exception:
            return 0

    def _recent_updates_projects() -> list[dict]:
        items = []
        for p in _proj_list:
            changelog = p / "CHANGELOG.md"
            if changelog.exists():
                lines = _read_lines_safe(changelog, 8)
                if lines:
                    items.append({
                        "project": p.name,
                        "mtime": changelog.stat().st_mtime,
                        "lines": lines,
                    })
        return sorted(items, key=lambda x: x["mtime"], reverse=True)

    if not _proj_list:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">📂</div>'
            '<div class="empty-text">No projects found. Projects will appear here once the agent starts working.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        # Summary stats
        _proj_active = [p for p in _proj_list if _project_status_fn(p)[0] == "IN_PROGRESS"]
        _proj_done = [p for p in _proj_list if _project_status_fn(p)[0] == "DONE"]
        _proj_review = [p for p in _proj_list if _project_status_fn(p)[0] == "PENDING_HUMAN_REVIEW"]

        st.markdown(
            f"""
            <div class="hero-grid">
                <div class="hero-stat"><div class="value">{len(_proj_list)}</div><div class="label">Total Projects</div></div>
                <div class="hero-stat"><div class="value">{len(_proj_active)}</div><div class="label">Active</div></div>
                <div class="hero-stat"><div class="value">{len(_proj_review)}</div><div class="label">Needs Review</div></div>
                <div class="hero-stat"><div class="value">{len(_proj_done)}</div><div class="label">Completed</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Filter / sort controls
        _proj_filter_cols = st.columns([2, 2, 1])
        with _proj_filter_cols[0]:
            _proj_search = st.text_input("Search projects", key="proj_search", placeholder="Filter by name…")
        with _proj_filter_cols[1]:
            _proj_status_filter = st.selectbox(
                "Status filter",
                ["All", "IN_PROGRESS", "DONE", "PENDING_HUMAN_REVIEW", "UNKNOWN"],
                key="proj_status_filter",
            )
        with _proj_filter_cols[2]:
            _proj_sort = st.selectbox("Sort", ["Recent first", "Name A→Z"], key="proj_sort")

        # Apply filters
        _proj_filtered = _proj_list[:]
        if _proj_search:
            _proj_filtered = [p for p in _proj_filtered if _proj_search.lower() in p.name.lower()]
        if _proj_status_filter != "All":
            _proj_filtered = [p for p in _proj_filtered if _project_status_fn(p)[0] == _proj_status_filter]
        if _proj_sort == "Name A→Z":
            _proj_filtered.sort(key=lambda p: p.name.lower())
        else:
            _proj_filtered.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        st.markdown(f'<div class="section-header">📂 Projects ({len(_proj_filtered)})</div>', unsafe_allow_html=True)

        if not _proj_filtered:
            st.caption("No projects match your filters.")
        else:
            # Project cards as glass cards
            _proj_cards_html = []
            for p in _proj_filtered[:12]:
                status, ts = _project_status_fn(p)
                file_count = _project_file_count(p)
                has_done = (p / "DONE.md").exists()
                has_changelog = (p / "CHANGELOG.md").exists()

                status_variant = "ok" if status == "IN_PROGRESS" else ("warn" if status == "PENDING_HUMAN_REVIEW" else ("ok" if status == "DONE" else "neutral"))
                status_icon = {"IN_PROGRESS": "🔄", "DONE": "✅", "PENDING_HUMAN_REVIEW": "⏳"}.get(status, "❓")
                badges = f'<span class="status-chip {status_variant}">{status_icon} {status}</span>'
                if has_done:
                    badges += ' <span class="status-chip ok">📋 DONE.md</span>'

                _proj_cards_html.append(
                    f"""
                    <div class="glass-card">
                        <div class="glass-title" style="font-size:1.05rem;">{p.name}</div>
                        <div style="margin:6px 0 8px;">{badges}</div>
                        <div class="glass-meta">Updated: {_fmt_time(ts) if ts else _fmt_mtime(p)}</div>
                        <div class="glass-meta">{file_count} files{'  ·  has changelog' if has_changelog else ''}</div>
                    </div>
                    """
                )
            st.markdown(f'<div class="glass-grid">{"".join(_proj_cards_html)}</div>', unsafe_allow_html=True)

            # Expandable detail for each project
            st.markdown('<div class="section-header">📋 Project Details</div>', unsafe_allow_html=True)
            for p in _proj_filtered[:12]:
                status, ts = _project_status_fn(p)
                changes = _project_recent_changes(p)
                with st.expander(f"**{p.name}** — {status} · {_fmt_time(ts) if ts else _fmt_mtime(p)}", expanded=False):
                    _det_cols = st.columns([1, 1])
                    with _det_cols[0]:
                        st.caption(f"Path: `{p}`")
                        st.caption(f"Files: {_project_file_count(p)}")
                        st.caption(f"Last modified: {_fmt_mtime(p)}")
                        if (p / "DONE.md").exists():
                            st.caption("✅ DONE.md present")
                    with _det_cols[1]:
                        if changes:
                            st.markdown("**Recent changelog**")
                            st.code("\n".join(changes), language="text")
                        else:
                            st.caption("No changelog entries yet.")
                    if status in ("PENDING_HUMAN_REVIEW", "DONE"):
                        st.markdown("**Review actions**")
                        action_cols = st.columns(2)
                        with action_cols[0]:
                            if status == "PENDING_HUMAN_REVIEW":
                                if st.button("Approve DONE", key=f"proj_done_{p.name}"):
                                    (p / "status.json").write_text(
                                        json.dumps({"status": "DONE", "timestamp": datetime.now(timezone.utc).isoformat(), "reason": "approved_done"}, indent=2),
                                        encoding="utf-8",
                                    )
                                    st.success("Marked DONE")
                                    st.rerun()
                        with action_cols[1]:
                            if st.button("Continue work", key=f"proj_continue_{p.name}"):
                                (p / "status.json").write_text(
                                    json.dumps({"status": "IN_PROGRESS", "timestamp": datetime.now(timezone.utc).isoformat(), "reason": "continue_work"}, indent=2),
                                    encoding="utf-8",
                                )
                                _write_continue_work_override(p.name, p)
                                _touch_trigger(f"continue_work:{p.name}")
                                st.warning("Set to IN_PROGRESS and queued a new proposal")
                                st.rerun()

        # Global recent updates feed
        st.divider()
        st.markdown('<div class="section-header">📡 Recent Updates Across Projects</div>', unsafe_allow_html=True)
        _proj_updates = _recent_updates_projects()
        if not _proj_updates:
            st.caption("No recent changelog entries found.")
        else:
            for item in _proj_updates[:8]:
                with st.expander(f"**{item['project']}** · {datetime.fromtimestamp(item['mtime'], tz=timezone.utc).astimezone(PST).strftime('%b %d, %H:%M')}", expanded=False):
                    st.code("\n".join(item["lines"]), language="text")

with tabs[2]:
    _page_context(
        "Inbox",
        "Agent directives and priorities — edit and save to guide the next cycle.",
    )
    _inbox_raw = read_inbox()
    _inbox_lines = [l for l in _inbox_raw.splitlines() if l.strip()]
    _inbox_count = len(_inbox_lines)
    _inbox_chars = len(_inbox_raw)
    _inbox_has_urgent = any(_inbox_is_urgent(l) for l in _inbox_lines)

    # Two-column layout: editor + preview/help
    _inbox_edit_col, _inbox_side_col = st.columns([2, 1], gap="large")

    with _inbox_edit_col:
        st.markdown(
            f"""
            <div class="inbox-shell">
              <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between;">
                <div style="display:flex; flex-wrap:wrap; gap:10px;">
                  <span class="pill"><strong>{_inbox_count}</strong>&nbsp;directives</span>
                  <span class="pill"><strong>{_inbox_chars:,}</strong>&nbsp;chars</span>
                  {f'<span class="pill urgent"><strong>⚠ Urgent</strong>&nbsp;items detected</span>' if _inbox_has_urgent else '<span class="pill"><strong>OK</strong>&nbsp;no urgent markers</span>'}
                </div>
                <div class="hint">One directive per line. Saved directives are read before each cycle.</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)

        inbox = st.text_area(
            "Inbox directives",
            value=_inbox_raw,
            height=460,
            key="inbox_editor",
            placeholder="Example:\nURGENT: Fix failing health probe on /health endpoint\nImprove Outputs page filtering by project\nAdd clearer call-to-action on Overview",
            label_visibility="collapsed",
        )
        _inbox_btn_cols = st.columns([1, 1, 2.2], gap="small")
        with _inbox_btn_cols[0]:
            if st.button("💾 Save directives", key="save_inbox", use_container_width=True):
                write_inbox(inbox)
                st.success("Saved. Next cycle will use these directives.")
        with _inbox_btn_cols[1]:
            if st.button("↩ Reload from disk", key="reload_inbox", use_container_width=True):
                st.rerun()
        with _inbox_btn_cols[2]:
            if st.button("🧹 Clean up whitespace", key="cleanup_inbox", use_container_width=True):
                cleaned = "\n".join([ln.rstrip() for ln in inbox.splitlines()]).strip() + ("\n" if inbox.strip() else "")
                st.session_state["inbox_editor"] = cleaned
                st.rerun()

    with _inbox_side_col:
        st.markdown('<div class="section-header" style="margin-top:0; font-size:0.95rem;">📋 Preview</div>', unsafe_allow_html=True)
        _preview_lines = [l for l in inbox.splitlines() if l.strip()]
        if _preview_lines:
            _preview_html_items = []
            for _pl in _preview_lines[:20]:
                _pl_escaped = _html.escape(_pl.strip())
                _is_urgent = _inbox_is_urgent(_pl)
                _preview_html_items.append(
                    f'<div class="inbox-line">'
                    f'  <span class="inbox-dot {"urgent" if _is_urgent else ""}"></span>'
                    f'  <span class="inbox-text">{_pl_escaped}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div class="inbox-preview">{"".join(_preview_html_items)}</div>',
                unsafe_allow_html=True,
            )
            if len(_preview_lines) > 20:
                st.caption(f"…and {len(_preview_lines) - 20} more directives")
        else:
            st.markdown(
                '<div class="inbox-preview"><div class="inbox-empty">Inbox is empty. Add directives to guide the agent.</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="inbox-help-card">
              <h4>💡 Writing good directives</h4>
              <div class="subtle">
                <div style="margin-bottom:8px;">
                  Keep each line atomic and testable. Prefer outcomes over vague intent.
                </div>
                <div class="kv-grid" style="margin:0;">
                  <span class="kv-key">Use</span><span class="kv-val">"Add a Health probe summary card"</span>
                  <span class="kv-key">Avoid</span><span class="kv-val warn">"Fix health tab"</span>
                  <span class="kv-key">Urgent marker</span><span class="kv-val error">URGENT: ...</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with tabs[3]:
    _page_context(
        "Outputs Library",
        "Browse proposals and reviews with search, filtering, and detail view.",
    )

    st.markdown(
        '<div style="font-size:0.82rem; color:var(--muted); margin-bottom:12px;">Tip: use the search box to filter by filename, then click any item to see full details.</div>',
        unsafe_allow_html=True,
    )
    all_files = list_matching(output_patterns())

    def _summarize_output(p: Path) -> dict[str, str]:
        try:
            data = read_json_file(p)
            return {
                "summary": str(data.get("summary", "")).strip(),
                "proposal_id": str(data.get("proposal_id", "")).strip(),
                "mode": str(data.get("mode", "")).strip(),
            }
        except Exception:
            return {"summary": "", "proposal_id": "", "mode": ""}

    def _project_key(meta: dict[str, str], filename: str) -> str:
        text = f"{meta.get('proposal_id','')} {meta.get('summary','')} {filename}".lower()
        if "dashboard" in text:
            return "agent-dashboard"
        if "runtime" in text:
            return "agent-runtime"
        return "general"

    def _clean_label(p: Path, meta: dict[str, str]) -> str:
        stamp = extract_timestamp(p).strftime("%Y-%m-%d %H:%M")
        kind = "Claude" if p.name.startswith("claude_") else "Review"
        short_id = meta.get("proposal_id", "")
        if short_id:
            short_id = short_id.replace("prop-", "").replace("proposal-", "")
            short_id = short_id.replace("review_", "").replace("__by_openai", "")
            short_id = short_id[:24]
            return f"{kind} · {stamp} · {short_id}"
        return f"{kind} · {stamp}"

    query = st.text_input("Search", help="Filter by filename...")
    sort_order = st.selectbox("Sort by", ["Newest first", "Oldest first", "Filename A→Z"])
    max_items = st.slider("Max items", min_value=5, max_value=100, value=20, step=5)

    filtered = [p for p in all_files if query.lower() in p.name.lower()] if query else all_files

    if not filtered:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">📄</div>'
            '<div class="empty-text">No matching proposal files found. Adjust your search or wait for the next cycle.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        claude_files = [p for p in all_files if p.name.startswith("claude_")]
        review_files = [p for p in all_files if p.name.startswith("review_")]
        latest_any = _latest_file(all_files)
        latest_review = _latest_file(review_files)

        if sort_order == "Oldest first":
            filtered_sorted = sorted(filtered, key=extract_timestamp)
        elif sort_order == "Filename A→Z":
            filtered_sorted = sorted(filtered, key=lambda p: p.name.lower())
        else:
            filtered_sorted = sorted(filtered, key=extract_timestamp, reverse=True)

        left_col, right_col = st.columns([1.05, 1.5], gap="large")

        with left_col:
            st.markdown("**Library overview**")
            stats_cols = st.columns(3)
            stats_cols[0].metric("Total", len(all_files))
            stats_cols[1].metric("Claude", len(claude_files))
            stats_cols[2].metric("Reviews", len(review_files))
            st.caption(f"Latest activity: {_fmt_time(stat_mtime_iso(latest_any)) if latest_any else '—'} · Latest review: {_fmt_time(stat_mtime_iso(latest_review)) if latest_review else '—'}")

            grouped: dict[str, list[Path]] = {}
            for p in filtered:
                meta = _summarize_output(p)
                key = _project_key(meta, p.name)
                grouped.setdefault(key, []).append(p)

            if grouped:
                st.markdown("**Project shortcuts**")
                proj_cols = st.columns(min(3, max(1, len(grouped))))
                for idx, (project, items) in enumerate(sorted(grouped.items())):
                    with proj_cols[idx % len(proj_cols)]:
                        st.caption(project)
                        latest = max(items, key=lambda x: extract_timestamp(x))
                        if st.button("Open latest", key=f"open_latest_{project}"):
                            st.session_state["selected_output"] = str(latest)
                            st.rerun()

            st.divider()
            st.markdown("**Output library**")

            label_map: dict[str, str] = {}
            meta_map: dict[str, dict[str, str]] = {}
            options = []
            for p in filtered_sorted[:max_items]:
                meta = _summarize_output(p)
                key = str(p)
                meta_map[key] = meta
                label_map[key] = _clean_label(p, meta)
                options.append(key)

            if "selected_output" not in st.session_state and options:
                st.session_state["selected_output"] = options[0]

            if options:
                selected = st.radio(
                    "Select an output",
                    options=options,
                    index=options.index(st.session_state.get("selected_output", options[0])),
                    format_func=lambda key: label_map.get(key, key),
                    label_visibility="collapsed",
                )
                st.session_state["selected_output"] = selected
                st.caption(f"Showing {min(len(options), max_items)} of {len(filtered)} matching files.")
            else:
                st.caption("No outputs available in this filter.")

        with right_col:
            sel = st.session_state.get("selected_output")
            if not sel:
                st.info("Select an output to view its details.")
            else:
                p = Path(sel)
                meta = _summarize_output(p)
                if p.name.startswith("review_"):
                    kind = "Review"
                elif p.name.startswith("openai_"):
                    kind = "OpenAI proposal"
                elif p.name.startswith("local_"):
                    kind = "Local proposal"
                elif p.name.startswith("codex_"):
                    kind = "Codex proposal"
                elif p.name.startswith("proposal_"):
                    kind = "Proposal"
                else:
                    kind = "Claude proposal"
                st.markdown(
                    f"""
                    <div class="glass-card">
                        <div class="glass-title">{p.name}</div>
                        <div class="glass-meta">{kind} · {_fmt_time(stat_mtime_iso(p))} · {p.stat().st_size:,} bytes</div>
                        <div class="glass-meta">Mode: {meta.get('mode') or '—'} · ID: {meta.get('proposal_id') or '—'}</div>
                        <div class="glass-meta">{meta.get('summary') or 'No summary provided.'}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("**Output JSON**")
                try:
                    payload = read_json_file(p)
                    decision = read_decision(p)
                    is_proposal = not p.name.startswith("review_")

                    if is_proposal and isinstance(payload, dict):
                        synopsis = _investor_synopsis(payload)
                        st.markdown("**Investor-style synopsis**")
                        st.markdown(
                            "\n".join(
                                [
                                    f"- **What it is:** {synopsis.get('what') or '—'}",
                                    f"- **Why now:** {synopsis.get('why') or '—'}",
                                    f"- **Edge:** {synopsis.get('edge') or '—'}",
                                    f"- **Next step:** {synopsis.get('next') or '—'}",
                                    f"- **Tech notes:** {synopsis.get('tech') or '—'}",
                                ]
                            )
                        )
                        st.markdown("**Proposal snapshot**")
                        st.write(payload.get("summary") or "—")
                        if payload.get("project"):
                            st.caption(f"Project: {payload.get('project')}")
                        if payload.get("overview"):
                            st.markdown("**Overview**")
                            st.caption(payload.get("overview") or "—")
                        if payload.get("project_summary"):
                            st.markdown("**Project summary**")
                            st.caption(payload.get("project_summary") or "—")
                        if payload.get("tech_details"):
                            st.markdown("**Tech details**")
                            st.caption(payload.get("tech_details") or "—")
                        if payload.get("definition_of_done"):
                            st.markdown("**Definition of Done**")
                            done_items = _as_list(payload.get("definition_of_done"))
                            if done_items:
                                st.markdown("\n".join([f"- {item}" for item in done_items]))
                            else:
                                st.caption("—")
                        if payload.get("context"):
                            st.markdown("**Context**")
                            st.caption(payload.get("context") or "—")
                        actions = _as_list(payload.get("suggested_actions"))
                        success = _as_list(payload.get("success_criteria"))
                        if actions:
                            st.markdown("**Suggested actions**")
                            st.markdown("\n".join([f"- {item}" for item in actions]))
                        if success:
                            st.markdown("**Success criteria**")
                            st.markdown("\n".join([f"- {item}" for item in success]))
                        conf = payload.get("confidence")
                        if conf is not None:
                            st.caption(f"Confidence: {conf}")

                    if decision:
                        st.markdown("**Decision**")
                        st.markdown(
                            f"- Status: **{decision.get('decision','—')}**\n"
                            f"- Time: {decision.get('timestamp','—')}\n"
                            f"- Note: {decision.get('note') or '—'}"
                        )
                        if decision.get("priority_path"):
                            st.caption(f"Approved priority: `{decision.get('priority_path')}`")

                    if is_proposal and isinstance(payload, dict):
                        st.markdown("**Approval controls**")
                        _gate_on = approval_gate_enabled()
                        note = st.text_input(
                            "Decision note (optional)",
                            key=f"decision_note_{p.name}",
                            placeholder="Why approve or reject?",
                        )
                        btn_cols = st.columns(3)
                        with btn_cols[0]:
                            if st.button("Approve proposal", key=f"approve_{p.name}"):
                                priority_path = write_priority_from_proposal(p, payload, note)
                                write_decision(
                                    p,
                                    "APPROVE",
                                    note=note,
                                    extra={"priority_path": str(priority_path)},
                                )
                                if _gate_on:
                                    trigger_run()
                                    st.success(f"Approved and queued. Priority saved to {priority_path}.")
                                else:
                                    st.success(f"Approved. Draft priority saved to {priority_path}.")
                                st.rerun()
                        with btn_cols[1]:
                            if st.button("Reject proposal", key=f"reject_{p.name}"):
                                write_decision(p, "REJECT", note=note)
                                st.warning("Rejected. Decision recorded.")
                                st.rerun()
                        with btn_cols[2]:
                            if (not _gate_on) and decision and decision.get("priority_path"):
                                if st.button("Promote to active", key=f"promote_{p.name}"):
                                    promoted = promote_priority(Path(decision["priority_path"]))
                                    trigger_run()
                                    st.success(f"Promoted to active priority: {promoted}")
                                    st.rerun()

                    st.json(payload)
                    st.download_button(
                        "Download JSON",
                        data=json.dumps(payload, indent=2),
                        file_name=p.name,
                        mime="application/json",
                    )
                except Exception as e:
                    st.error(f"Failed to read JSON: {e}")
                    st.code(p.read_text(encoding="utf-8")[:12000])

with tabs[4]:
    _page_context(
        "Timeline",
        "Proposal activity over time — daily, weekly, and monthly breakdowns.",
    )

    files = list_matching(output_patterns())

    def _counts_last_days(days: int = 14) -> dict[str, int]:
        today = datetime.now().date()
        counts: dict[str, int] = {
            (today - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(days - 1, -1, -1)
        }
        for p in files:
            dt = extract_timestamp(p).date().strftime("%Y-%m-%d")
            if dt in counts:
                counts[dt] += 1
        return counts

    def _current_streak(counts: dict[str, int]) -> int:
        streak = 0
        for day in reversed(list(counts.keys())):
            if counts[day] > 0:
                streak += 1
            else:
                break
        return streak

    def _bucket_day(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    def _bucket_week(dt: datetime) -> str:
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def _bucket_month(dt: datetime) -> str:
        return dt.strftime("%Y-%m")

    def _count_by(bucket_fn):
        counts: dict[str, int] = {}
        for p in files:
            dt = extract_timestamp(p)
            key = bucket_fn(dt)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    if not files:
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">📈</div>'
            '<div class="empty-text">No proposal files found yet. The timeline will populate as the agent generates proposals.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.write(f"Total proposals: {len(files)}")
        last_14 = _counts_last_days(14)
        total_14 = sum(last_14.values())
        most_active_day = max(last_14.items(), key=lambda x: x[1])
        streak = _current_streak(last_14)
        cols = st.columns(3)
        cols[0].metric("Total (14d)", total_14)
        cols[1].metric("Most active day", most_active_day[0], delta=f"{most_active_day[1]} proposals")
        cols[2].metric("Current streak", f"{streak} day(s)")
        st.markdown("**Daily activity (14 days)**")
        st.bar_chart(last_14)

        day_counts = _count_by(_bucket_day)
        week_counts = _count_by(_bucket_week)
        month_counts = _count_by(_bucket_month)

        def _render_table(title: str, data: dict[str, int]):
            st.markdown(f"**{title}**")
            if not data:
                st.write("No data.")
                return
            rows = "\n".join([f"| {k} | {v} |" for k, v in data.items()])
            st.markdown("| Period | Count |\n|---|---|\n" + rows)

        _render_table("Per day", day_counts)
        _render_table("Per week", week_counts)
        _render_table("Per month", month_counts)

with tabs[5]:
    _page_context(
        "Settings & Control",
        "Agent mode, diagnostics, and review controls.",
    )
    _settings_left, _settings_right = st.columns([1, 1], gap="large")

    with _settings_left:
        # ── Agent Mode ───────────────────────────────────────────
        st.markdown(
            '<div class="settings-section">'
            '<h4>🎯 Agent Mode</h4>'
            '</div>',
            unsafe_allow_html=True,
        )
        current_mode = read_mode()
        _mode_desc = {
            "DIRECTED": "Agent follows inbox directives strictly. Best for focused work.",
            "AUTONOMOUS": "Agent self-selects improvements. Best for exploration.",
        }
        mode = st.radio(
            "Operating mode",
            ["DIRECTED", "AUTONOMOUS"],
            index=0 if current_mode == "DIRECTED" else 1,
            help=_mode_desc.get(current_mode, ""),
        )
        st.caption(_mode_desc.get(mode, ""))
        if mode != current_mode:
            write_mode(mode)
            st.success(f"Mode → {mode}")

        st.markdown("")  # spacer

        # ── Cycle Control ────────────────────────────────────────
        st.markdown(
            '<div class="settings-section">'
            '<h4>⚡ Cycle Control</h4>'
            '</div>',
            unsafe_allow_html=True,
        )
        _set_last_cycle = _last_cycle_ts()
        if _set_last_cycle:
            _set_age = (datetime.now(timezone.utc) - _set_last_cycle).total_seconds() / 60.0
            _set_age_str = f"{_set_age:.0f}m ago" if _set_age < 60 else f"{_set_age/60:.1f}h ago"
            st.caption(f"Last cycle: {_fmt_time(_set_last_cycle.isoformat())} ({_set_age_str})")
        else:
            st.caption("No cycle history yet.")

        _trig_cols = st.columns(2)
        with _trig_cols[0]:
            if st.button("⚡ Trigger run", use_container_width=True):
                trigger_run()
                st.success("Triggered ✓")
        with _trig_cols[1]:
            if st.button("🔄 Kick cycle", key="settings_kick", use_container_width=True):
                _touch_trigger("settings_kick")
                st.success("Cycle kicked ✓")

    with _settings_right:
        # ── Diagnostics ─────────────────────────────────────────
        st.markdown(
            '<div class="settings-section">'
            '<h4>🔍 Diagnostics</h4>'
            '</div>',
            unsafe_allow_html=True,
        )
        provider, model = _active_provider_model()
        credit_status, credit_note = _credit_snapshot()
        _cred_variant = "ok" if credit_status == "ok" else ("warn" if credit_status == "low" else "neutral")
        st.markdown(
            f"""
            <div class="kv-grid">
                <span class="kv-key">Provider</span>
                <span class="kv-val">{provider.upper() if provider else 'UNKNOWN'}</span>
                <span class="kv-key">Model</span>
                <span class="kv-val">{model}</span>
                <span class="kv-key">Credits</span>
                <span class="kv-val {_cred_variant}">{credit_status.upper()}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(credit_note)

        if st.button("🧪 Test OpenClaw", use_container_width=True):
            models, default_model = _openclaw_models()
            if not models:
                st.error("OpenClaw model not configured.")
            else:
                with st.spinner("Testing…"):
                    try:
                        out = generate(default_model, "Reply with: OK", timeout=30)
                        st.success(f"OpenClaw OK: {out.strip()[:50]}")
                    except Exception as e:
                        st.error(f"Test failed: {e}")

        st.markdown("")  # spacer

        # ── Review Controls ──────────────────────────────────────
        st.markdown(
            '<div class="settings-section">'
            '<h4>📋 Review Controls</h4>'
            '</div>',
            unsafe_allow_html=True,
        )
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    current_status = "UNKNOWN"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            current_status = data.get("status", "UNKNOWN")
        except Exception:
            current_status = "UNKNOWN"
    _status_variant = "ok" if current_status == "IN_PROGRESS" else ("warn" if current_status == "PENDING_HUMAN_REVIEW" else ("ok" if current_status == "DONE" else "neutral"))
    st.markdown(
        f'<div style="margin-bottom:10px;">'
        f'<span class="status-chip {_status_variant}">{current_status}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if current_status == "PENDING_HUMAN_REVIEW":
        st.warning("Review required — the agent is waiting for your decision.")
    _rev_cols = st.columns(2)
    with _rev_cols[0]:
        if st.button("✅ Approve (DONE)", use_container_width=True):
            _confirm_done()

    with _rev_cols[1]:
        if st.button("▶️ Continue work", use_container_width=True):
            _confirm_continue()

with tabs[6]:
    _page_context(
        "AI Chat",
        "Conversational interface powered by the local OpenClaw agent.",
    )

    models, default_model = _openclaw_models()
    if not models:
        st.error("OpenClaw model not configured. Check ~/.openclaw/openclaw.json.")
    else:
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        if st.session_state["chat_history"]:
            st.markdown(f"**Conversation history** ({len(st.session_state['chat_history']) // 2} exchanges)")
            for msg in st.session_state["chat_history"][-10:]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        model = st.selectbox("Model", models, index=models.index(default_model) if default_model in models else 0)

        # Use session state for prompt to survive quick-prompt reruns
        _default_prompt = st.session_state.pop("_qp_prompt", "")
        prompt = st.text_area("Prompt", value=_default_prompt, height=220, help="Ask anything (local-only).", key="chat_prompt_area")
        if _default_prompt:
            st.info("Quick prompt loaded — click 'Send to OpenClaw' to run it.")
        
        # Contextual quick prompts
        st.markdown("**Quick prompts**")
        qp_cols = st.columns(3)
        with qp_cols[0]:
            if st.button("📊 Summarize status", key="qp_status", use_container_width=True):
                _qp_inbox = read_inbox().strip()
                _qp_projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
                _qp_statuses = []
                if _qp_projects_root.exists():
                    for _qp_p in _qp_projects_root.iterdir():
                        if _qp_p.is_dir():
                            _qp_sp = _qp_p / "status.json"
                            if _qp_sp.exists():
                                try:
                                    _qp_d = json.loads(_qp_sp.read_text(encoding="utf-8"))
                                    _qp_statuses.append(f"{_qp_p.name}: {_qp_d.get('status', '?')}")
                                except Exception:
                                    pass
                prompt = f"Summarize the current state of my projects and suggest what to focus on next.\n\nProject statuses:\n" + "\n".join(_qp_statuses) + f"\n\nInbox:\n{_qp_inbox[:2000]}"
                st.session_state["_qp_prompt"] = prompt
                st.rerun()
            if st.button("🐛 Debug last failure", key="qp_debug", use_container_width=True):
                _qp_failures = _recent_failures(1)
                _qp_fail_text = _qp_failures[0][:1500] if _qp_failures else "(no recent failures)"
                prompt = f"Analyze this CI/build failure and suggest a fix:\n\n{_qp_fail_text}"
                st.session_state["_qp_prompt"] = prompt
                st.rerun()
        with qp_cols[2]:
            if st.button("📝 Draft changelog", key="qp_changelog", use_container_width=True):
                _qp_feed = _activity_feed(limit=10)
                _qp_feed_text = "\n".join(f"- {i['ts']}: {i['summary']}" for i in _qp_feed) if _qp_feed else "(no activity)"
                prompt = f"Write a concise changelog entry based on these recent activities:\n\n{_qp_feed_text}"
                st.session_state["_qp_prompt"] = prompt
                st.rerun()

        if st.button("Send to OpenClaw"):
            if not prompt.strip():
                st.warning("Type a prompt first.")
            else:
                with st.spinner("Thinking..."):
                    out = chat(model, prompt, timeout=90)
                st.session_state["chat_history"].append({"role": "user", "content": prompt})
                st.session_state["chat_history"].append({"role": "assistant", "content": out})
                st.rerun()

        col_clear, col_export = st.columns(2)
        with col_clear:
            if st.session_state.get("chat_history") and st.button("Clear history"):
                st.session_state["chat_history"] = []
                st.rerun()
        with col_export:
            if st.session_state.get("chat_history") and st.button("Copy conversation"):
                export = "\n\n".join(
                    f"**{m['role'].upper()}**: {m['content']}"
                    for m in st.session_state["chat_history"]
                )
                st.code(export, language="markdown")

with tabs[7]:
    _page_context(
        "System Logs",
        "Browse and inspect recent log files from the agent runtime.",
    )

    st.caption("Browse recent log files from the agent runtime.")

    logs_dir = Path("/home/hackerman/agent-runtime/logs")

    def _list_log_files(directory: Path, max_files: int = 50) -> list[Path]:
        if not directory.exists():
            return []
        log_files = []
        for ext in ("*.jsonl", "*.log", "*.txt", "*.diff"):
            log_files.extend(directory.glob(ext))
        return sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]

    def _tail_file(path: Path, max_lines: int = 100) -> str:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception as e:
            return f"(error reading file: {e})"

    def _parse_jsonl_entries(path: Path, max_entries: int = 50) -> list[dict]:
        entries = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines[-200:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"_raw": line})
                if len(entries) >= max_entries:
                    break
        except Exception:
            pass
        return entries

    if not logs_dir.exists():
        st.warning(f"Logs directory not found: {logs_dir}")
    else:
        log_files = _list_log_files(logs_dir)
        if not log_files:
            st.info("No log files found.")
        else:
            col_filter, col_lines = st.columns([3, 1])
            with col_filter:
                selected_log = st.selectbox(
                    "Log file",
                    log_files,
                    format_func=lambda p: f"{p.name}  ({_fmt_mtime(p)}, {p.stat().st_size:,} bytes)",
                    key="log_file_select",
                )
            with col_lines:
                tail_lines = st.number_input("Tail lines", min_value=10, max_value=500, value=80, step=10)

            if selected_log:
                st.caption(f"Showing last {tail_lines} lines of **{selected_log.name}**")

                if selected_log.suffix == ".jsonl":
                    view_mode = st.radio("View mode", ["Structured", "Raw"], horizontal=True, key="log_view_mode")
                    if view_mode == "Structured":
                        entries = _parse_jsonl_entries(selected_log, max_entries=tail_lines)
                        if not entries:
                            st.info("No entries parsed.")
                        else:
                            for i, entry in enumerate(entries[:40]):
                                if "_raw" in entry:
                                    st.code(entry["_raw"], language="text")
                                else:
                                    event = entry.get("event", "")
                                    ts = entry.get("timestamp", entry.get("ts", ""))
                                    rc = entry.get("returncode", "")
                                    label = f"{_fmt_time(ts) if ts else '—'} · {event}" + (f" · rc={rc}" if rc != "" else "")
                                    with st.expander(label, expanded=(i == 0)):
                                        st.json(entry)
                    else:
                        content = _tail_file(selected_log, max_lines=tail_lines)
                        st.code(content, language="json")
                elif selected_log.suffix == ".diff":
                    content = _tail_file(selected_log, max_lines=tail_lines)
                    st.code(content, language="diff")
                else:
                    content = _tail_file(selected_log, max_lines=tail_lines)
                    st.code(content, language="text")

                if st.button("Refresh", key="log_refresh"):
                    st.rerun()

with tabs[8]:
    _page_context(
        "System Health",
        "Reliability metrics, cycle frequency, and patch success rates.",
    )


    # ── Cycle stats ──────────────────────────────────────────────
    cycle_log = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")

    def _parse_cycle_events(limit: int = 500) -> list[dict]:
        if not cycle_log.exists():
            return []
        events: list[dict] = []
        try:
            lines = cycle_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-limit:]):
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
        except Exception:
            pass
        return events

    cycle_events = _parse_cycle_events(500)

    autopatch_events = [e for e in cycle_events if e.get("event") == "autopatch"]
    successes = [e for e in autopatch_events if e.get("returncode") == 0]
    failures_list = [e for e in autopatch_events if e.get("returncode") != 0]

    total_patches = len(autopatch_events)
    success_count = len(successes)
    fail_count = len(failures_list)
    success_rate = (success_count / total_patches * 100) if total_patches else 0

    h_cols = st.columns(4)
    h_cols[0].metric("Total patches", total_patches)
    h_cols[1].metric("Succeeded", success_count)
    h_cols[2].metric("Failed", fail_count)
    h_cols[3].metric("Success rate", f"{success_rate:.0f}%")

    # ── Uptime / cycle frequency ─────────────────────────────────
    cycle_starts = [e for e in cycle_events if e.get("event") == "cycle_start"]

    def _ts_dt(obj: dict) -> datetime | None:
        ts = obj.get("ts", "")
        if not ts:
            return None
        try:
            s = ts.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except Exception:
            return None

    if cycle_starts:
        recent_starts = []
        for cs in cycle_starts[:50]:
            dt = _ts_dt(cs)
            if dt:
                recent_starts.append(dt)
        if len(recent_starts) >= 2:
            recent_starts.sort()
            gaps = [(recent_starts[i+1] - recent_starts[i]).total_seconds() / 60.0
                    for i in range(len(recent_starts) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            min_gap = min(gaps)
            max_gap = max(gaps)
            st.markdown("**Cycle frequency** (recent)")
            freq_cols = st.columns(3)
            freq_cols[0].metric("Avg interval", f"{avg_gap:.1f} min")
            freq_cols[1].metric("Min interval", f"{min_gap:.1f} min")
            freq_cols[2].metric("Max interval", f"{max_gap:.1f} min")
        else:
            st.caption("Not enough cycle starts to compute frequency.")
    else:
        st.caption("No cycle_start events found.")

    # ── Daily success/fail chart ─────────────────────────────────
    st.divider()
    st.markdown("**Daily patch outcomes (last 14 days)**")

    today = datetime.now(timezone.utc).date()
    day_labels = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    day_ok: dict[str, int] = {d: 0 for d in day_labels}
    day_fail: dict[str, int] = {d: 0 for d in day_labels}

    for e in autopatch_events:
        dt = _ts_dt(e)
        if not dt:
            continue
        d = dt.date().isoformat()
        if d in day_ok:
            if e.get("returncode") == 0:
                day_ok[d] += 1
            else:
                day_fail[d] += 1

    import pandas as pd
    chart_df = pd.DataFrame({
        "Succeeded": day_ok,
        "Failed": day_fail,
    })
    st.bar_chart(chart_df)

    # ── Recent failures detail ───────────────────────────────────
    st.divider()
    st.markdown("**Recent failures**")
    if not failures_list:
        st.success("No recent failures — all patches succeeded.")
    else:
        for evt in failures_list[:5]:
            ts = evt.get("ts", "")
            rc = evt.get("returncode", "?")
            stderr = evt.get("stderr", "")[:300]
            with st.expander(f"{_fmt_time(ts)} · rc={rc}", expanded=False):
                st.json(evt)
                if stderr:
                    st.code(stderr, language="text")

    # ── OpenClaw connectivity ────────────────────────────────────
    st.divider()
    st.markdown("**OpenClaw connectivity**")
    _models, _default_model = _openclaw_models()
    if not _models:
        st.error("OpenClaw model not configured.")
    else:
        st.success(f"OpenClaw ready — default model: {_default_model}")
        st.caption(f"Models in config: {', '.join(_models[:5])}")

    # ── Endpoint health probes ───────────────────────────────────
    st.divider()
    st.markdown("**Endpoint health probes**")
    endpoints = [
        ("OpenClaw gateway", "http://127.0.0.1:18789/health", False),
        ("Local Llama /health", "http://127.0.0.1:11434/health", True),
        ("Local Llama models", "http://127.0.0.1:11434/v1/models", False),
    ]
    for label, url, expect_json in endpoints:
        status, note = _http_probe(url, expect_json_status=expect_json, timeout=2)
        if status == "ok":
            st.success(f"{label}: {note}")
        elif status == "warn":
            st.warning(f"{label}: {note}")
        else:
            st.error(f"{label}: {note}")

    if st.button("Refresh health", key="health_refresh"):
        st.rerun()


with tabs[9]:
    _page_context(
        "Daily Digest",
        "AI-generated summary of recent agent activity.",
    )

    st.caption("A comprehensive summary of recent agent activity, generated via the local OpenClaw agent.")

    def _gather_digest_context(days: int = 1) -> str:
        """Collect recent events, inbox, and changelog entries for digest."""
        parts: list[str] = []

        # Recent cycle events
        cycle_log = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
        if cycle_log.exists():
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            recent_events: list[str] = []
            try:
                lines = cycle_log.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in reversed(lines[-300:]):
                    try:
                        obj = json.loads(line)
                        ts = obj.get("ts", "")
                        if ts:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt < cutoff:
                                break
                        recent_events.append(f"  {_summarize_event(obj)} ({ts})")
                    except Exception:
                        continue
            except Exception:
                pass
            if recent_events:
                parts.append("RECENT CYCLE EVENTS:\n" + "\n".join(recent_events[:30]))

        # Router events
        router_log = Path("/home/hackerman/agent-runtime/logs/router_events.jsonl")
        if router_log.exists():
            router_items: list[str] = []
            try:
                lines = router_log.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in reversed(lines[-100:]):
                    try:
                        obj = json.loads(line)
                        router_items.append(f"  {_summarize_event(obj)} ({obj.get('ts', '')})")
                    except Exception:
                        continue
            except Exception:
                pass
            if router_items:
                parts.append("ROUTER EVENTS:\n" + "\n".join(router_items[:15]))

        # Inbox
        inbox_text = read_inbox().strip()
        if inbox_text:
            parts.append(f"INBOX:\n{inbox_text[:3000]}")

        # Recent changelogs
        updates = _recent_updates_global(max_lines=6)
        if updates:
            cl_parts = []
            for u in updates[:4]:
                cl_parts.append(f"  [{u['project']}] " + " | ".join(u["lines"][:3]))
            parts.append("RECENT CHANGELOG ENTRIES:\n" + "\n".join(cl_parts))

        # Project statuses
        projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
        if projects_root.exists():
            statuses: list[str] = []
            for p in projects_root.iterdir():
                if p.is_dir():
                    sp = p / "status.json"
                    if sp.exists():
                        try:
                            data = json.loads(sp.read_text(encoding="utf-8"))
                            statuses.append(f"  {p.name}: {data.get('status', '?')}")
                        except Exception:
                            pass
            if statuses:
                parts.append("PROJECT STATUSES:\n" + "\n".join(statuses))

        return "\n\n".join(parts) if parts else "(no data available)"

    digest_models, _digest_default = _openclaw_models()
    if not digest_models:
        st.warning("OpenClaw model not configured. Add it to enable digest generation.")
    else:
        d_col1, d_col2 = st.columns([2, 1])
        with d_col1:
            digest_model = st.selectbox("Model", digest_models, index=0, key="digest_model")
        with d_col2:
            digest_days = st.selectbox("Time range", [1, 3, 7], index=0, format_func=lambda d: f"Last {d} day(s)", key="digest_days")

        if st.button("Generate digest", key="gen_digest"):
            context = _gather_digest_context(days=digest_days)
            digest_prompt = (
                "You are an engineering manager's assistant. Write a concise daily digest based on the data below.\n\n"
                "Structure your response as:\n"
                "## Status Overview\nOne-paragraph executive summary.\n\n"
                "## Key Events\nBulleted list of the most important things that happened.\n\n"
                "## Issues & Risks\nAnything that failed, is blocked, or needs attention.\n\n"
                "## Next Steps\nRecommended actions.\n\n"
                f"DATA:\n{context[:10000]}"
            )
            with st.spinner("Generating digest…"):
                try:
                    digest_out = generate(digest_model, digest_prompt, timeout=120)
                    st.session_state["digest"] = digest_out
                    st.session_state["digest_ts"] = datetime.now(PST).strftime("%b %d, %H:%M:%S")
                except Exception as e:
                    st.error(f"Digest generation failed: {e}")

        if "digest" in st.session_state:
            st.markdown(st.session_state["digest"])
            st.caption(f"Generated at {st.session_state.get('digest_ts', '—')}")

            # Export digest
            d_exp_cols = st.columns(3)
            with d_exp_cols[0]:
                _copy_button(st.session_state["digest"], key="copy_digest")
            with d_exp_cols[1]:
                st.download_button(
                    "📥 Download as Markdown",
                    data=f"# Daily Digest — {st.session_state.get('digest_ts', 'unknown')}\n\n{st.session_state['digest']}",
                    file_name=f"digest_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                )

# ── Notes tab ────────────────────────────────────────────────────
with tabs[10]:
    _page_context(
        "Notes & Scratchpad",
        "Persistent notes for yourself. Pinned note shows in the sidebar.",
    )


    _notes_dir = APP_ROOT / "notes"
    _notes_dir.mkdir(exist_ok=True)
    _pin_path = APP_ROOT / "pinned_note.txt"

    # Pinned note editor
    st.markdown("### 📌 Pinned Note")
    st.caption("This appears in the sidebar for quick reference.")
    _pin_current = ""
    if _pin_path.exists():
        try:
            _pin_current = _pin_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    _pin_new = st.text_area(
        "Pinned note",
        value=_pin_current,
        height=100,
        key="pinned_note_edit",
        help="Example: focus on health tab styling today",
    )
    if st.button("Save pinned note", key="save_pin"):
        try:
            _pin_path.write_text(_pin_new, encoding="utf-8")
            st.success("Pinned note saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")

    st.divider()

    # Scratchpad notes (timestamped)
    st.markdown("### 📝 Scratchpad")
    st.caption("Quick timestamped notes. Saved as individual files.")

    _new_note = st.text_area(
        "New note",
        height=120,
        key="new_scratch_note",
        help="Type a note and click Save.",
    )
    if st.button("Save note", key="save_scratch"):
        if _new_note.strip():
            ts = datetime.now(timezone.utc)
            fname = f"note_{ts.strftime('%Y%m%d_%H%M%S')}.md"
            fpath = _notes_dir / fname
            try:
                content = f"# Note — {ts.astimezone(PST).strftime('%b %d, %Y %H:%M')}\n\n{_new_note.strip()}\n"
                fpath.write_text(content, encoding="utf-8")
                st.success(f"Saved: {fname}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save note: {e}")
        else:
            st.warning("Write something first.")

    # List existing notes
    _existing_notes = sorted(_notes_dir.glob("note_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if _existing_notes:
        st.divider()
        st.markdown(f"**Saved notes** ({len(_existing_notes)})")
        for _np in _existing_notes[:20]:
            try:
                _nc = _np.read_text(encoding="utf-8", errors="ignore")
                _first_line = _nc.strip().splitlines()[0] if _nc.strip() else _np.name
                with st.expander(f"{_first_line}  ·  {_fmt_mtime(_np)}", expanded=False):
                    st.markdown(_nc)
                    _del_col, _pin_col = st.columns(2)
                    with _del_col:
                        if st.button("🗑️ Delete", key=f"del_{_np.name}"):
                            _np.unlink()
                            st.rerun()
                    with _pin_col:
                        if st.button("📌 Pin this", key=f"pin_{_np.name}"):
                            # Extract content without the header
                            _lines = _nc.strip().splitlines()
                            _body = "\n".join(_lines[1:]).strip() if len(_lines) > 1 else _nc.strip()
                            _pin_path.write_text(_body[:200], encoding="utf-8")
                            st.success("Pinned!")
                            st.rerun()
            except Exception:
                st.caption(f"Could not read {_np.name}")
    else:
        st.caption("No saved notes yet.")

# ── Footer ───────────────────────────────────────────────────────
st.markdown(
    f'<div class="dashboard-footer">'
    f'Agent Runtime Dashboard · {datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")} · '
    f'Autonomous Engineering Control Center'
    f'</div>',
    unsafe_allow_html=True,
)

# Auto-refresh implementation
if st.session_state.get("auto_refresh"):
    import time
    time.sleep(0.1)  # small delay to let page render
    st.markdown(
        '<meta http-equiv="refresh" content="30">',
        unsafe_allow_html=True,
    )

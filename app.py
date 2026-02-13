from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
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
from lib import finance as fin

APP_ROOT = Path(__file__).parent
LOGO_PATH = APP_ROOT / "assets" / "logo.svg"
ICON_PATH = APP_ROOT / "assets" / "icon.png"
PST = ZoneInfo("America/Los_Angeles")

page_icon = str(ICON_PATH) if ICON_PATH.exists() else ":)"
st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide", page_icon=page_icon, initial_sidebar_state="auto")

def _set_flash(kind: str, msg: str) -> None:
    st.session_state["_flash"] = {"kind": kind, "msg": msg}

def _render_flash() -> None:
    flash = st.session_state.pop("_flash", None)
    if not flash:
        return
    kind = flash.get("kind", "info")
    msg = flash.get("msg", "")
    {"success": st.success, "warning": st.warning, "error": st.error}.get(kind, st.info)(msg)

# ── Global CSS ───────────────────────────────────────────────────
st.markdown(
    """
    <style>
    :root {
        --bg: #050705;
        --bg-gradient-a: #0a140a;
        --bg-gradient-b: #050705;
        --bg-gradient-c: #030403;
        --panel: rgba(7, 12, 7, 0.75);
        --panel-hover: rgba(12, 22, 12, 0.88);
        --panel-solid: #0a150a;
        --accent: #39ff14;
        --accent-bright: #5cff3e;
        --accent-soft: rgba(57, 255, 20, 0.14);
        --accent-border: rgba(57, 255, 20, 0.22);
        --accent-glow: rgba(57, 255, 20, 0.30);
        --text: #eaffea;
        --text-heading: #f0fff0;
        --muted: #9ddc9d;
        --danger: #ff5c5c;
        --danger-soft: rgba(255, 92, 92, 0.12);
        --warn: #ffb347;
        --warn-soft: rgba(255, 179, 71, 0.12);
        --success: #39ff14;
        --success-soft: rgba(57, 255, 20, 0.12);
        --radius: 10px;
        --radius-lg: 14px;
        --shadow-sm: 0 2px 8px rgba(0,0,0,0.22);
        --shadow-md: 0 4px 20px rgba(0,0,0,0.32);
        --shadow-lg: 0 8px 32px rgba(0,0,0,0.42);
        --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    }
    .stApp {
        background: linear-gradient(145deg, var(--bg-gradient-a) 0%, var(--bg-gradient-b) 50%, var(--bg-gradient-c) 100%);
        color: var(--text); font-family: var(--font);
    }
    h1, h2, h3, h4 { color: var(--text-heading); }
    .stMarkdown, .stCaption, .stText, .stTextArea textarea { color: var(--text); }
    /* Push content below Streamlit toolbar and hide deploy chrome */
    .block-container { padding-top: 3.5rem; }
    header[data-testid="stHeader"] { background: var(--bg) !important; }
    .stDeployButton, [data-testid="stToolbar"] {
        display: none !important;
    }

    .stButton>button {
        background: var(--accent-soft); border: 1px solid var(--accent-border);
        color: var(--accent-bright); border-radius: var(--radius);
        font-weight: 600; font-size: 0.82rem; box-shadow: var(--shadow-sm);
        transition: background 180ms ease, border-color 180ms ease;
    }
    .stButton>button:hover {
        background: rgba(57, 255, 20, 0.22); border-color: var(--accent);
    }
    div[data-baseweb="select"] > div {
        background: var(--panel) !important; border-color: var(--accent-border) !important;
    }

    .card-title-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:6px;}
    .card-title-row .title{font-weight:700;font-size:1.02rem;color:var(--accent-bright);margin:0;}
    .card-title-row .meta{font-size:0.74rem;color:var(--muted);opacity:0.85;white-space:nowrap;}
    .subtle{font-size:0.78rem;color:var(--muted);line-height:1.6;opacity:0.85;}
    .glass-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:12px 0 20px;}
    .glass-card {
        padding:18px 20px; border-radius:var(--radius-lg);
        background:var(--panel); border:1px solid rgba(57,255,20,0.15);
        backdrop-filter: blur(12px);
    }
    .glass-title{font-weight:600;font-size:0.95rem;margin-bottom:6px;color:var(--accent-bright);}
    .glass-meta{opacity:0.8;font-size:0.8rem;color:var(--muted);line-height:1.5;}

    .pulse {
        display:inline-block;width:10px;height:10px;border-radius:999px;
        margin-right:8px;background:var(--accent);
        box-shadow:0 0 12px var(--accent-glow);
        animation:pulse 1.8s ease-in-out infinite;
    }
    @keyframes pulse {
        0%{transform:scale(0.85);opacity:0.5;}
        50%{transform:scale(1.15);opacity:1;}
        100%{transform:scale(0.85);opacity:0.5;}
    }

    .topbar {
        position:sticky; top:0; z-index:80; margin:0 0 16px; padding:14px 18px;
        border-radius:var(--radius-lg); background:rgba(7,12,7,0.65);
        border:1px solid var(--accent-border); backdrop-filter:blur(14px) saturate(1.2);
        box-shadow:var(--shadow-lg);
    }
    .topbar-row{display:flex;align-items:center;gap:14px;justify-content:space-between;flex-wrap:wrap;}
    .topbar-left{display:flex;align-items:center;gap:14px;min-width:260px;flex:1;}
    .topbar-title{display:flex;flex-direction:column;gap:2px;min-width:0;}
    .topbar-title .h{margin:0;padding:0;font-size:1.4rem;font-weight:800;letter-spacing:-0.02em;color:var(--text-heading);line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .topbar-title .sub{font-size:0.72rem;color:var(--muted);opacity:0.7;letter-spacing:0.08em;text-transform:uppercase;}
    .topbar-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end;}
    .topbar-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
    .topbar-actions .stButton>button{padding:6px 12px;border-radius:var(--radius);font-size:0.82rem;min-height:36px;}

    .meta-chip {
        display:inline-flex;align-items:center;gap:8px;padding:5px 12px;
        border-radius:999px;border:1px solid rgba(157,220,157,0.2);
        background:rgba(7,12,7,0.5);color:var(--muted);font-size:0.75rem;white-space:nowrap;
    }
    .meta-chip strong{color:var(--text);font-weight:700;}
    .meta-chip .dot{width:8px;height:8px;border-radius:999px;background:var(--muted);opacity:0.5;box-shadow:none;flex-shrink:0;}
    .meta-chip.ok .dot{background:var(--success);opacity:1;box-shadow:0 0 8px rgba(52,211,153,0.35);}
    .meta-chip.warn .dot{background:var(--warn);opacity:1;box-shadow:0 0 8px rgba(255,179,71,0.3);}
    .meta-chip.error .dot{background:var(--danger);opacity:1;box-shadow:0 0 8px rgba(255,92,92,0.3);}
    .meta-chip.neutral .dot{background:var(--muted);opacity:0.5;box-shadow:none;}

    .data-strip{
        display:flex;flex-wrap:wrap;gap:10px;padding:10px 14px;margin:8px 0 14px;
        border-radius:var(--radius-lg);background:rgba(7,12,7,0.5);
        border:1px solid var(--accent-border);backdrop-filter:blur(8px);
    }
    .section-header{font-size:1.1rem;font-weight:700;color:var(--accent-bright);margin:24px 0 10px;padding:0 0 8px;border-bottom:1px solid var(--accent-border);letter-spacing:0.02em;}

    [data-testid="stMetricValue"]{color:var(--accent-bright)!important;font-weight:700;font-size:1.4rem!important;}
    [data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:0.78rem!important;text-transform:uppercase;letter-spacing:0.06em;}
    [data-testid="stMetricDelta"]{font-size:0.75rem!important;}
    div[data-testid="metric-container"]{background:var(--panel);border:1px solid var(--accent-border);border-radius:var(--radius);padding:14px 16px 10px;backdrop-filter:blur(8px);}

    div[data-baseweb="tab-list"]{background:rgba(7,12,7,0.6);border:1px solid var(--accent-border);border-radius:var(--radius);padding:4px 6px;gap:2px;backdrop-filter:blur(8px);overflow-x:auto;scrollbar-width:thin;scrollbar-color:var(--accent-border) transparent;}
    div[data-baseweb="tab-list"]::-webkit-scrollbar{height:4px;}
    div[data-baseweb="tab-list"]::-webkit-scrollbar-thumb{background:var(--accent-border);border-radius:4px;}
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]{background:transparent!important;border:1px solid transparent!important;border-radius:8px!important;color:var(--muted)!important;font-weight:500!important;font-size:0.82rem!important;padding:7px 14px!important;transition:all 150ms ease!important;white-space:nowrap;}
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]:hover{background:var(--accent-soft)!important;color:var(--accent-bright)!important;border-color:var(--accent-border)!important;}
    div[data-baseweb="tab-list"] button[aria-selected="true"]{background:var(--accent-soft)!important;border:1px solid var(--accent)!important;color:var(--accent-bright)!important;font-weight:700!important;box-shadow:0 0 12px var(--accent-glow)!important;}
    div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none!important;}

    .status-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;letter-spacing:0.03em;line-height:1;white-space:nowrap;}
    .status-chip.ok{background:var(--success-soft);border:1px solid rgba(52,211,153,0.35);color:var(--success);}
    .status-chip.warn{background:var(--warn-soft);border:1px solid rgba(255,179,71,0.35);color:var(--warn);}
    .status-chip.error{background:var(--danger-soft);border:1px solid rgba(255,92,92,0.35);color:var(--danger);}
    .status-chip.neutral{background:rgba(157,220,157,0.10);border:1px solid rgba(157,220,157,0.25);color:var(--muted);}

    .activity-timeline{display:flex;flex-direction:column;gap:0;margin:8px 0 4px;}
    .activity-item{display:flex;align-items:flex-start;gap:12px;padding:8px 0;position:relative;}
    .activity-item:not(:last-child){border-left:2px solid var(--accent-border);margin-left:5px;padding-left:16px;}
    .activity-item:last-child{border-left:2px solid transparent;margin-left:5px;padding-left:16px;}
    .activity-dot{position:absolute;left:-4px;top:12px;width:10px;height:10px;border-radius:50%;background:var(--accent);border:2px solid var(--bg);box-shadow:0 0 8px var(--accent-glow);flex-shrink:0;}
    .activity-dot.dimmed{background:var(--muted);box-shadow:none;opacity:0.4;}
    .activity-content{flex:1;min-width:0;}
    .activity-ts{font-size:0.72rem;color:var(--muted);opacity:0.7;}
    .activity-text{font-size:0.82rem;color:var(--text);line-height:1.4;}

    details[data-testid="stExpander"]{border:1px solid var(--accent-border)!important;border-radius:var(--radius)!important;background:var(--panel)!important;}
    details[data-testid="stExpander"] summary{color:var(--text)!important;font-weight:500;}
    hr{border:none!important;border-top:1px solid var(--accent-border)!important;margin:20px 0!important;}

    section[data-testid="stSidebar"]{background:rgba(5,8,5,0.95)!important;border-right:1px solid var(--accent-border);}
    section[data-testid="stSidebar"]>div:first-child{padding-top:1rem;}
    section[data-testid="stSidebar"] .stButton>button{font-size:0.82rem;}

    .stTextArea textarea,.stTextInput input{background:rgba(7,12,7,0.65)!important;border-color:var(--accent-border)!important;color:var(--text)!important;border-radius:8px!important;}
    .stTextArea textarea:focus,.stTextInput input:focus{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(57,255,20,0.12)!important;}
    div[data-testid="stChatMessage"]{background:var(--panel)!important;border:1px solid var(--accent-border)!important;border-radius:var(--radius)!important;margin-bottom:8px;}
    div[data-testid="stAlert"]{border-radius:var(--radius)!important;font-size:0.85rem!important;}
    pre{background:rgba(5,8,5,0.8)!important;border:1px solid var(--accent-border)!important;border-radius:8px!important;}
    div[data-baseweb="radio"] label span{color:var(--text)!important;}
    .stDownloadButton>button{background:transparent!important;border:1px solid var(--accent)!important;color:var(--accent-bright)!important;}
    .stDownloadButton>button:hover{background:var(--accent-soft)!important;}

    .page-context-bar{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;margin:0 0 16px;border-radius:var(--radius);background:rgba(7,12,7,0.5);border:1px solid var(--accent-border);font-size:0.8rem;color:var(--muted);}
    .page-context-bar .ctx-title{font-weight:700;color:var(--accent-bright);font-size:0.9rem;}
    .page-context-bar .ctx-meta{opacity:0.8;}
    .empty-state{text-align:center;padding:48px 24px;color:var(--muted);opacity:0.65;}
    .empty-state .empty-icon{font-size:2.5rem;margin-bottom:10px;}
    .empty-state .empty-text{font-size:0.9rem;}
    .dashboard-footer{text-align:center;padding:20px 0 8px;font-size:0.7rem;color:var(--muted);opacity:0.4;border-top:1px solid var(--accent-border);margin-top:40px;}

    .sb-status-card{border:1px solid var(--accent-border);border-radius:var(--radius);padding:12px 14px;margin-bottom:14px;background:rgba(7,12,7,0.55);backdrop-filter:blur(8px);}
    .sb-status-row{display:flex;align-items:center;gap:8px;font-size:0.82rem;padding:3px 0;}
    .sb-status-row .sb-icon{width:18px;text-align:center;flex-shrink:0;}
    .sb-status-row .sb-label{color:var(--muted);min-width:52px;}
    .sb-status-row .sb-value{color:var(--text);font-weight:600;}
    .sb-status-row .sb-value.ok{color:var(--success);}
    .sb-status-row .sb-value.warn{color:var(--warn);}
    .sb-status-row .sb-value.error{color:var(--danger);}
    .sb-status-row .sb-value.neutral{color:var(--muted);}
    .sb-divider{border:none;border-top:1px solid var(--accent-border);margin:10px 0;}
    .sb-section-label{font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);opacity:0.55;margin:14px 0 6px;padding-left:2px;}

    section[data-testid="stSidebar"] .stButton>button{font-size:0.8rem;padding:6px 12px;border-radius:8px;width:100%;justify-content:flex-start;gap:8px;}
    section[data-testid="stSidebar"] .sb-link-btn{display:block;width:100%;text-align:left;font-size:0.8rem;padding:6px 12px;border-radius:8px;color:var(--text);background:rgba(7,12,7,0.45);border:1px solid var(--accent-border);text-decoration:none;font-weight:600;transition:all 0.2s ease;box-sizing:border-box;}
    section[data-testid="stSidebar"] .sb-link-btn:hover{background:var(--accent-soft);border-color:var(--accent);}

    .inbox-shell{display:flex;flex-direction:column;gap:10px;padding:14px 16px;border-radius:var(--radius-lg);background:var(--panel);border:1px solid var(--accent-border);backdrop-filter:blur(12px);box-shadow:var(--shadow-md);}
    .inbox-shell .hint{font-size:0.78rem;color:var(--muted);opacity:0.8;line-height:1.5;}
    .inbox-help-card{padding:14px 16px;border-radius:var(--radius-lg);background:rgba(7,12,7,0.45);border:1px solid var(--accent-border);backdrop-filter:blur(8px);}
    .inbox-help-card h4{margin:0 0 8px;font-size:0.9rem;color:var(--accent-bright);letter-spacing:0.02em;}
    .pill{display:inline-flex;align-items:center;gap:8px;padding:5px 10px;border-radius:999px;border:1px solid var(--accent-border);background:rgba(7,12,7,0.5);color:var(--muted);font-size:0.74rem;white-space:nowrap;}
    .pill strong{color:var(--text);font-weight:700;}
    .pill.urgent{border-color:rgba(255,92,92,0.35);color:rgba(255,180,180,0.95);}
    .pill.urgent strong{color:var(--danger);}
    .inbox-preview{border:1px solid var(--accent-border);border-radius:var(--radius-lg);background:rgba(5,8,5,0.4);padding:10px 12px;max-height:420px;overflow:auto;}
    .inbox-line{display:flex;gap:10px;align-items:flex-start;padding:7px 6px;border-radius:var(--radius);transition:background 140ms ease;border:1px solid transparent;}
    .inbox-line:hover{background:var(--accent-soft);border-color:var(--accent-border);}
    .inbox-dot{margin-top:3px;width:10px;height:10px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent-glow);flex-shrink:0;}
    .inbox-dot.urgent{background:var(--danger);box-shadow:0 0 8px rgba(255,92,92,0.3);}
    .inbox-text{font-size:0.82rem;color:var(--text);line-height:1.45;word-break:break-word;}
    .inbox-empty{padding:26px 10px;text-align:center;color:var(--muted);opacity:0.65;font-size:0.85rem;}
    .inbox-toolbar{display:flex;align-items:center;gap:10px;margin:0 0 12px;flex-wrap:wrap;}
    .inbox-toolbar .inbox-stat{font-size:0.78rem;color:var(--muted);padding:4px 12px;border:1px solid var(--accent-border);border-radius:8px;background:rgba(7,12,7,0.45);}
    .inbox-toolbar .inbox-stat strong{color:var(--accent-bright);font-weight:700;}

    .settings-section{padding:18px 20px;border-radius:var(--radius-lg);background:var(--panel);border:1px solid var(--accent-border);backdrop-filter:blur(12px);margin-bottom:16px;}
    .settings-section h4{margin:0 0 10px;font-size:0.95rem;color:var(--accent-bright);}
    .kv-grid{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;font-size:0.82rem;margin:6px 0 10px;}
    .kv-grid .kv-key{color:var(--muted);white-space:nowrap;}
    .kv-grid .kv-val{color:var(--text);font-weight:600;}
    .kv-grid .kv-val.ok{color:var(--success);}
    .kv-grid .kv-val.warn{color:var(--warn);}
    .kv-grid .kv-val.error{color:var(--danger);}

    /* ── Command Center ───────────────────────────── */
    .cmd-center{
        padding:16px 20px;margin:0 0 20px;border-radius:var(--radius-lg);
        background:linear-gradient(135deg,rgba(7,12,7,0.8) 0%,rgba(10,20,10,0.65) 100%);
        border:1px solid var(--accent-border);backdrop-filter:blur(14px);
        box-shadow:0 0 20px rgba(57,255,20,0.06);
    }
    .cmd-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
    .cmd-status{display:flex;align-items:center;gap:10px;min-width:200px;}
    .cmd-status .pulse-dot{
        width:12px;height:12px;border-radius:50%;flex-shrink:0;
        animation:pulse 1.8s ease-in-out infinite;
    }
    .cmd-status .pulse-dot.live{background:var(--success);box-shadow:0 0 14px rgba(57,255,20,0.5);}
    .cmd-status .pulse-dot.idle{background:var(--warn);box-shadow:0 0 10px rgba(255,179,71,0.35);}
    .cmd-status .pulse-dot.error{background:var(--danger);box-shadow:0 0 10px rgba(255,92,92,0.35);}
    .cmd-status .status-label{font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;}
    .cmd-status .status-label.live{color:var(--success);}
    .cmd-status .status-label.idle{color:var(--warn);}
    .cmd-status .status-label.error{color:var(--danger);}
    .cmd-metrics{display:flex;gap:20px;flex:1;flex-wrap:wrap;justify-content:flex-end;}
    .cmd-metric{text-align:center;min-width:90px;}
    .cmd-metric .val{font-size:1.15rem;font-weight:800;color:var(--accent-bright);line-height:1.2;font-family:'SF Mono',Monaco,Consolas,monospace;}
    .cmd-metric .val.up{color:var(--success);}
    .cmd-metric .val.down{color:var(--danger);}
    .cmd-metric .lbl{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;opacity:0.7;}
    .cmd-divider{width:1px;height:32px;background:var(--accent-border);flex-shrink:0;}

    /* ── Alert Cards ──────────────────────────────── */
    .alert-card{
        display:flex;align-items:flex-start;gap:12px;padding:12px 16px;
        border-radius:var(--radius);margin:6px 0;
        transition:opacity 0.2s ease;
    }
    .alert-card.critical{background:rgba(255,92,92,0.08);border:1px solid rgba(255,92,92,0.25);}
    .alert-card.warning{background:rgba(255,179,71,0.08);border:1px solid rgba(255,179,71,0.25);}
    .alert-card.info{background:rgba(57,255,20,0.05);border:1px solid rgba(57,255,20,0.15);}
    .alert-icon{font-size:1.1rem;flex-shrink:0;margin-top:1px;}
    .alert-body{flex:1;min-width:0;}
    .alert-title{font-size:0.82rem;font-weight:700;line-height:1.3;}
    .alert-card.critical .alert-title{color:var(--danger);}
    .alert-card.warning .alert-title{color:var(--warn);}
    .alert-card.info .alert-title{color:var(--success);}
    .alert-detail{font-size:0.75rem;color:var(--muted);margin-top:2px;line-height:1.4;}
    .alert-ts{font-size:0.65rem;color:var(--muted);opacity:0.5;margin-top:4px;}

    /* ── Terminal Log ─────────────────────────────── */
    .term-log{
        font-family:'SF Mono',Monaco,Consolas,'Courier New',monospace;
        font-size:0.75rem;line-height:1.65;
        background:rgba(2,4,2,0.9);border:1px solid var(--accent-border);
        border-radius:var(--radius);padding:12px 14px;
        max-height:400px;overflow-y:auto;
        scrollbar-width:thin;scrollbar-color:var(--accent-border) transparent;
    }
    .term-log::-webkit-scrollbar{width:6px;}
    .term-log::-webkit-scrollbar-thumb{background:var(--accent-border);border-radius:3px;}
    .term-line{display:flex;gap:8px;padding:2px 0;border-bottom:1px solid rgba(57,255,20,0.04);}
    .term-line:hover{background:rgba(57,255,20,0.04);}
    .term-ln{color:var(--muted);opacity:0.35;min-width:28px;text-align:right;user-select:none;}
    .term-ts{color:var(--muted);opacity:0.5;min-width:120px;}
    .term-lvl{min-width:48px;font-weight:700;text-transform:uppercase;}
    .term-lvl.trade{color:var(--success);}
    .term-lvl.swap{color:#0af;}
    .term-lvl.bet{color:#c084fc;}
    .term-lvl.alert{color:var(--warn);}
    .term-lvl.error{color:var(--danger);}
    .term-lvl.info{color:var(--muted);}
    .term-lvl.decision{color:#f0abfc;}
    .term-lvl.research{color:#67e8f9;}
    .term-msg{color:var(--text);flex:1;word-break:break-word;}

    /* ── Position Card (enhanced) ─────────────────── */
    .pos-card{
        padding:16px 18px;border-radius:var(--radius-lg);
        background:var(--panel);border:1px solid rgba(57,255,20,0.15);
        backdrop-filter:blur(12px);transition:border-color 0.2s ease;
    }
    .pos-card:hover{border-color:var(--accent);}
    .pos-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;}
    .pos-sym{font-weight:800;font-size:1.05rem;color:var(--accent-bright);font-family:'SF Mono',Monaco,Consolas,monospace;}
    .pos-chain{font-size:0.68rem;color:var(--muted);opacity:0.6;text-transform:uppercase;letter-spacing:0.06em;}
    .pos-metrics{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:0.78rem;margin-top:6px;}
    .pos-metrics .pm-label{color:var(--muted);}
    .pos-metrics .pm-val{font-weight:700;color:var(--text);text-align:right;font-family:'SF Mono',Monaco,Consolas,monospace;}
    .pos-metrics .pm-val.up{color:var(--success);}
    .pos-metrics .pm-val.down{color:var(--danger);}
    .pos-pnl{margin-top:8px;padding-top:8px;border-top:1px solid rgba(57,255,20,0.1);text-align:center;}
    .pos-pnl .pnl-val{font-size:1.1rem;font-weight:800;font-family:'SF Mono',Monaco,Consolas,monospace;}
    .pos-pnl .pnl-val.up{color:var(--success);}
    .pos-pnl .pnl-val.down{color:var(--danger);}
    .pos-pnl .pnl-label{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;}
    </style>
    """,
    unsafe_allow_html=True,
)
_render_flash()

def _page_context(title: str, description: str = "", extra_html: str = "") -> None:
    meta = f'<span class="ctx-meta">{description}</span>' if description else ""
    extra = f'<span class="ctx-meta">{extra_html}</span>' if extra_html else ""
    st.markdown(f'<div class="page-context-bar"><span class="ctx-title">{title}</span>{meta}{extra}</div>', unsafe_allow_html=True)

def _variant_from_health(health: str) -> str:
    if health == "ok": return "ok"
    if health in ("warn", "unknown"): return "warn"
    if health == "error": return "error"
    return "neutral"

def _variant_from_project_status(status: str) -> str:
    if status in ("IN_PROGRESS", "DONE"): return "ok"
    if status == "PENDING_HUMAN_REVIEW": return "warn"
    return "neutral"

def _latest_file(files: Iterable[Path]) -> Path | None:
    latest: Path | None = None
    latest_ts: datetime | None = None
    for p in files:
        dt = extract_timestamp(p)
        if not latest_ts or dt > latest_ts:
            latest = p
            latest_ts = dt
    return latest

def _decision_status(p: Path) -> str:
    decision = read_decision(p)
    if not decision: return ""
    return str(decision.get("decision", "")).strip().upper()

def _is_decided(p: Path) -> bool:
    return _decision_status(p) in ("APPROVE", "REJECT")

def _latest_pending(files: Iterable[Path]) -> Path | None:
    pending = [p for p in files if not _is_decided(p)]
    return _latest_file(pending)

def _fmt_time(value: str | datetime | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(PST).strftime("%b %d, %H:%M")
    if isinstance(value, str) and value.strip():
        s = value.strip()
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
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
    if not log_path.exists(): return "unknown", "no cycle log found"
    last_status = "unknown"
    last_reason = ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-200:]):
            if "\"event\": \"autopatch\"" in line:
                if "\"returncode\": 0" in line:
                    last_status = "ok"; last_reason = "last autopatch succeeded"
                else:
                    last_status = "error"; last_reason = "last autopatch failed"
                break
        if last_status == "unknown": last_reason = "no autopatch event yet"
    except Exception:
        last_status = "unknown"; last_reason = "failed to parse cycle log"
    return last_status, last_reason

def _last_autopatch_success_ts() -> datetime | None:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists(): return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"autopatch\"" in line and "\"returncode\": 0" in line:
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts")
                    if ts: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception: continue
    except Exception: return None
    return None

def _latest_routing() -> dict:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists(): return {}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"routing\"" in line:
                try: return json.loads(line)
                except Exception: continue
    except Exception: return {}
    return {}

def _routing_config() -> dict:
    cfg_path = Path("/home/hackerman/agent-runtime/constitution/agent_routing.json")
    if not cfg_path.exists(): return {}
    try: return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception: return {}

def _openclaw_models() -> tuple[list[str], str]:
    cfg_path = Path("/home/hackerman/.openclaw/openclaw.json")
    cfg: dict = {}
    if cfg_path.exists():
        try: cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception: cfg = {}
    providers = cfg.get("models", {}).get("providers", {})
    local = providers.get("local-llama", {})
    models = [m.get("id") for m in local.get("models", []) if isinstance(m, dict) and m.get("id")]
    primary = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
    default = primary.split("/", 1)[-1] if primary else (models[0] if models else "llama-3.1-8b-instruct")
    if default not in models: models = [default] + [m for m in models if m != default]
    return models, default

def _active_provider_model() -> tuple[str, str]:
    cfg = _routing_config()
    routing = _latest_routing()
    provider = (routing.get("provider") or cfg.get("force_provider") or cfg.get("default_provider") or "unknown").strip().lower()
    model = "—"
    if provider == "codex": model = str(cfg.get("codex_model", "gpt-5.2-codex"))
    elif provider == "claude": model = str(cfg.get("claude_model", "claude-opus-4-6"))
    elif provider == "openai": model = str(cfg.get("openai_model", "gpt-5.2"))
    return provider, model

def _credit_snapshot() -> tuple[str, str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/autopatch_events.jsonl")
    if not log_path.exists(): return "unknown", "No credit signal found."
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
                    detail = line.lower(); ts = None
                if "credit" in detail or "billing" in detail or "quota" in detail:
                    if ts:
                        try: last_credit_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except Exception: last_credit_ts = None
                    if last_credit_ts: break
        last_ok = _last_autopatch_success_ts()
        if last_credit_ts and last_ok and last_ok > last_credit_ts: return "ok", "No recent billing issues."
        if last_credit_ts: return "low", "Billing/credit issue detected recently."
        return "unknown", "No billing issues detected."
    except Exception: return "unknown", "Unable to parse credit log."

def _read_project_status() -> tuple[str, str]:
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if projects_root.exists():
        for p in sorted(projects_root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_dir(): continue
            sp = p / "status.json"
            if sp.exists():
                try:
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    st_val = data.get("status", "")
                    if st_val == "IN_PROGRESS": return st_val, data.get("timestamp", "")
                except Exception: continue
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    if not status_path.exists(): return "UNKNOWN", "status file missing"
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        return data.get("status", "UNKNOWN"), data.get("timestamp", "")
    except Exception: return "UNKNOWN", "failed to parse status file"

def _cycle_label(health: str, project_status: str) -> tuple[str, str]:
    if health == "error" and project_status == "IN_PROGRESS":
        return "warn", "recent failure (work resumed)"
    return health, ""

def _last_cycle_ts() -> datetime | None:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists(): return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"cycle_start\"" in line or "\"event\": \"autopatch\"" in line:
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts")
                    if ts: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception: continue
    except Exception: return None
    return None

def _touch_trigger(note: str) -> None:
    trigger_path = Path("/home/hackerman/agent-runtime/directives/priorities/.trigger")
    try:
        ts = datetime.now(timezone.utc).isoformat()
        with trigger_path.open("a", encoding="utf-8") as f:
            f.write(f"{note} {ts}\n")
    except Exception: pass

def _inbox_is_urgent(line: str) -> bool:
    s = (line or "").strip().lower()
    if not s: return False
    if s.startswith(("urgent:", "critical:", "blocker:", "asap:", "hotfix:")): return True
    if "!!!" in s: return True
    return any(kw in s for kw in (" urgent", " critical", " blocker", " asap", "sev1", "sev-1"))

def _latest_patch_name() -> str:
    logs = Path("/home/hackerman/agent-runtime/logs")
    if not logs.exists(): return "—"
    items = sorted(logs.glob("dashboard_patch_*.diff"), key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0].name if items else "—"

def _recent_updates_global(max_lines: int = 8) -> list[dict]:
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if not projects_root.exists(): return []
    items = []
    for p in projects_root.iterdir():
        if not p.is_dir(): continue
        changelog = p / "CHANGELOG.md"
        if changelog.exists():
            try:
                lines = changelog.read_text(encoding="utf-8", errors="ignore").splitlines()
                lines = [ln for ln in lines if ln.strip()][:max_lines]
                if lines: items.append({"project": p.name, "mtime": changelog.stat().st_mtime, "lines": lines})
            except Exception: continue
    return sorted(items, key=lambda x: x["mtime"], reverse=True)

def _write_continue_work_override(project: str, project_path: Path) -> Path:
    overrides_dir = Path("/home/hackerman/agent-runtime/directives/overrides")
    overrides_dir.mkdir(parents=True, exist_ok=True)
    override_path = overrides_dir / f"continue_work_{project}.md"
    override_path.write_text(
        "# Continue Work\n"
        f"Project: {project}\nPath: {project_path}\n\n"
        "Generate a new improvement proposal based on the latest project state. "
        "Study WORK_ORDER.md and current code, identify gaps vs the existing Definition of Done, "
        "and propose the next iteration with clear steps and updated Definition of Done.\n",
        encoding="utf-8",
    )
    return override_path

def _project_choices() -> list[str]:
    root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if not root.exists(): return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])

def _codex_audit_overrides() -> list[Path]:
    overrides_dir = Path("/home/hackerman/agent-runtime/directives/overrides")
    if not overrides_dir.exists(): return []
    return sorted(overrides_dir.glob("allow_codex_audit*.md"))

def _set_codex_audit_override(project: str | None) -> Path:
    overrides_dir = Path("/home/hackerman/agent-runtime/directives/overrides")
    overrides_dir.mkdir(parents=True, exist_ok=True)
    for p in _codex_audit_overrides():
        try: p.unlink()
        except Exception: pass
    name = f"allow_codex_audit_{project}.md" if project else "allow_codex_audit.md"
    path = overrides_dir / name
    path.write_text(f"# Allow Codex Audit\nProject: {project or 'all'}\nRequested at: {datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    return path

def _clear_codex_audit_overrides() -> None:
    for p in _codex_audit_overrides():
        try: p.unlink()
        except Exception: pass

def _recent_failures(limit: int = 3) -> list[str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")
    if not log_path.exists(): return []
    failures: list[str] = []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-400:]):
            if "\"event\": \"autopatch\"" in line and "\"returncode\": 0" not in line:
                failures.append(line)
            if len(failures) >= limit: break
    except Exception: return []
    return failures

def _dismissed_errors_path() -> Path:
    return Path("/home/hackerman/agent-runtime/logs/dismissed_errors.json")

def _load_dismissed_errors() -> set[str]:
    path = _dismissed_errors_path()
    if not path.exists(): return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list): return set(str(x) for x in data)
    except Exception: return set()
    return set()

def _save_dismissed_errors(ids: set[str]) -> None:
    try: _dismissed_errors_path().write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
    except Exception: pass

def _error_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]

def _copy_button(text: str, key: str) -> None:
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    badge_id = f"copy_badge_{key}"
    btn_id = f"copy_btn_{key}"
    html_str = f"""
    <style>html,body{{margin:0;padding:0;background:transparent;}}
    .copy-btn{{background:transparent;border:1px solid #39ff14;color:#39ff14;padding:6px 10px;border-radius:8px;cursor:pointer;font-weight:600;}}
    .copy-btn.copied{{color:#050705;background:#39ff14;}}
    .copy-badge{{margin-left:8px;font-size:0.7rem;color:#39ff14;opacity:0;transition:opacity 120ms ease;}}</style>
    <div style="display:flex;align-items:center;gap:6px;">
      <button id="{btn_id}" class="copy-btn" onclick="
        const btn=this;const badge=document.getElementById('{badge_id}');
        navigator.clipboard.writeText(`{safe}`).then(()=>{{
          btn.classList.add('copied');btn.innerText='COPIED';badge.innerText='Copied';badge.style.opacity=1;
          setTimeout(()=>{{btn.classList.remove('copied');btn.innerText='⧉';badge.style.opacity=0;}},1100);
        }}).catch(()=>{{badge.innerText='Blocked';badge.style.opacity=1;setTimeout(()=>{{badge.style.opacity=0;}},1500);}});
      ">⧉</button>
      <span id="{badge_id}" class="copy-badge">Copied</span>
    </div>"""
    components.html(html_str, height=34, width=120)

def _summarize_event(evt: dict) -> str:
    event = evt.get("event", "")
    if event == "proposal_ok":
        return f"{evt.get('planner', 'claude').capitalize()} drafted a proposal ({evt.get('proposal_id', 'unknown')})."
    if event == "review_written":
        return f"{evt.get('critic', 'codex').capitalize()} reviewed the proposal."
    if event == "proposal_skipped": return "No new projects; proposal step skipped."
    if event == "executor_run":
        return f"Executor applied a patch and ran checks ({_latest_patch_name()})." if evt.get("returncode") == 0 else "Executor failed during patch/checks."
    if event == "autopatch":
        return "Autopatch succeeded (diff generated)." if evt.get("returncode") == 0 else "Autopatch failed to produce a valid diff."
    if event == "check":
        return f"Validation check: {evt.get('name', 'check')} {'passed' if evt.get('passed') else 'failed'}."
    if event == "done": return "Marked ready for review (all gates satisfied)."
    if event == "in_progress": return "Cycle completed; continuing work (more improvements needed)."
    if event == "routing":
        return f"Routed this cycle to {evt.get('provider', 'unknown').upper()} for the next patch."
    return "Activity updated."

def _parse_event_lines(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists(): return []
    items: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-limit:]):
            try: obj = json.loads(line)
            except Exception: continue
            if "event" in obj: items.append(obj)
    except Exception: return []
    return items

def _agent_activity() -> tuple[str, str]:
    router_items = _parse_event_lines(Path("/home/hackerman/agent-runtime/logs/router_events.jsonl"), limit=200)
    cycle_items = _parse_event_lines(Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl"), limit=400)
    items = router_items[:5] + cycle_items[:5]
    if not items: return "unknown", "no activity logs found"
    def _ts_dt(obj):
        ts = obj.get("ts", "")
        if not ts: return None
        try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception: return None
    items.sort(key=lambda obj: _ts_dt(obj) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    latest = items[0]
    summary = _summarize_event(latest)
    status = "active"
    if latest.get("event") in ("proposal_skipped",): status = "idle"
    latest_dt = _ts_dt(latest)
    if latest_dt:
        age_min = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 60.0
        if age_min >= 60:
            status = "idle"
            hrs = int(age_min // 60); mins = int(age_min % 60)
            age_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
            summary = f"{summary} (last activity {age_str} ago)"
    return status, summary

def _activity_feed(limit: int = 6) -> list[dict]:
    items = (_parse_event_lines(Path("/home/hackerman/agent-runtime/logs/router_events.jsonl"), limit=200)
             + _parse_event_lines(Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl"), limit=400))
    if not items: return []
    items.sort(key=lambda obj: obj.get("ts", ""), reverse=True)
    return [{"ts": obj.get("ts", ""), "summary": _summarize_event(obj)} for obj in items[:limit]]

def _chip(label: str, variant: str) -> str:
    return f'<span class="status-chip {variant}">{label}</span>'

def _first_sentence(text: str) -> str:
    if not text: return ""
    for sep in (". ", ".\n", ".\t"):
        if sep in text: return text.split(sep, 1)[0].strip() + "."
    return text.strip()

def _as_list(value) -> list[str]:
    if isinstance(value, list): return [str(v).strip() for v in value if str(v).strip()]
    if value: return [str(value).strip()]
    return []

def _tech_notes(payload: dict) -> str:
    text = " ".join([str(payload.get("summary") or ""), str(payload.get("context") or ""),
        str(payload.get("reasoning") or ""), " ".join(_as_list(payload.get("suggested_actions")))]).lower()
    keywords = ["solana","base","evm","supabase","postgres","postgresql","next.js","react","tailwind",
        "streamlit","wallet","multisig","safe","squads","intent","policy","approval","api","sdk",
        "dashboard","agent","automation","workflow","python"]
    found = [k for k in keywords if k in text]
    return ", ".join(sorted(set(found))) if found else "—"

def _edge_from_text(payload: dict) -> str:
    text = " ".join([str(payload.get("summary") or ""), str(payload.get("context") or ""), str(payload.get("reasoning") or "")]).lower()
    if "approval" in text or "policy" in text or "audit" in text: return "Safety-first approvals and audit trail."
    if "speed" in text or "fast" in text: return "Speed to execution with clear guardrails."
    if "accuracy" in text: return "Trustworthy reporting and visibility."
    return "Clear scope + rapid iteration."

def _proposal_text(payload: dict) -> str:
    return str(payload.get("proposal_text") or payload.get("proposal") or "").strip()

def _template_section(text: str, label: str) -> str:
    if not text: return ""
    idx = text.lower().find(label.lower())
    if idx == -1: return ""
    start = idx + len(label)
    m = re.search(r"\n\d+\)\s", text[start:], re.IGNORECASE)
    end = start + m.start() if m else len(text)
    return text[start:end].strip()

def _stack_summary(payload: dict) -> str:
    stack = payload.get("stack_summary") if isinstance(payload, dict) else None
    if not isinstance(stack, dict): return "—"
    parts = []
    for label, key in [("Languages", "languages"), ("Frameworks", "frameworks"), ("Data", "data"), ("Infra", "infra")]:
        vals = stack.get(key) or []
        if isinstance(vals, list) and vals: parts.append(f"{label}: {', '.join([str(v) for v in vals])}")
    return " · ".join(parts) if parts else "—"

def _investor_synopsis(payload: dict) -> dict[str, str]:
    summary = str(payload.get("summary") or "").strip()
    proposal_text = _proposal_text(payload)
    exec_block = _template_section(proposal_text, "1) EXECUTIVE SUMMARY (HUMAN READ)") or _template_section(proposal_text, "1) EXECUTIVE SUMMARY")
    exec_map = {}
    for line in [ln.strip() for ln in exec_block.splitlines() if ln.strip().startswith("- ")]:
        if ":" in line:
            key, val = line[2:].split(":", 1)
            exec_map[key.strip().lower()] = val.strip()
    context = str(payload.get("context") or "").strip()
    reasoning = str(payload.get("reasoning") or "").strip()
    actions = _as_list(payload.get("suggested_actions"))
    stack_note = _stack_summary(payload)
    return {
        "what": exec_map.get("what we're building") or summary or _first_sentence(context),
        "why": exec_map.get("expected outcome") or _first_sentence(reasoning) or _first_sentence(context),
        "edge": exec_map.get("why it wins (differentiator)") or _edge_from_text(payload),
        "next": actions[0] if actions else "Review proposal details.",
        "tech": stack_note or _tech_notes(payload),
    }

def _project_status_summary(project_path: Path) -> tuple[str, str]:
    status_path = project_path / "status.json"
    done_path = project_path / "DONE.md"
    work_order = project_path / "WORK_ORDER.md"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            return str(data.get("status") or "UNKNOWN"), str(data.get("reason") or "")
        except Exception: return "UNKNOWN", "status.json unreadable"
    if done_path.exists(): return "DONE", "DONE.md present"
    if work_order.exists(): return "IN_PROGRESS", "work order present"
    return "UNKNOWN", "no status file"

def _project_last_activity(project_name: str, project_path: Path) -> datetime | None:
    candidates = [project_path / f for f in ("status.json", "WORK_ORDER.md", "DONE.md", "CHANGELOG.md", "README.md")]
    log_path = Path("/home/hackerman/agent-runtime/logs") / f"{project_name}_cycle.jsonl"
    if log_path.exists(): candidates.append(log_path)
    latest = None
    for p in candidates:
        if not p.exists(): continue
        try: ts = p.stat().st_mtime
        except Exception: continue
        if latest is None or ts > latest: latest = ts
    return datetime.fromtimestamp(latest, tz=timezone.utc) if latest else None

def _list_projects_overview() -> list[dict]:
    root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if not root.exists(): return []
    items = []
    for p in sorted([d for d in root.iterdir() if d.is_dir()]):
        status, reason = _project_status_summary(p)
        last_dt = _project_last_activity(p.name, p)
        items.append({"name": p.name, "path": str(p), "status": status, "reason": reason, "last": last_dt})
    return items

def _project_status_detail(project_path: Path) -> tuple[str, str, str]:
    status_path = project_path / "status.json"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            return str(data.get("status") or "UNKNOWN"), str(data.get("reason") or ""), str(data.get("timestamp") or "")
        except Exception: return "UNKNOWN", "status.json unreadable", ""
    if (project_path / "DONE.md").exists(): return "DONE", "DONE.md present", ""
    if (project_path / "WORK_ORDER.md").exists(): return "IN_PROGRESS", "work order present", ""
    return "UNKNOWN", "no status file", ""

def _project_agent_hint(project_path: Path) -> str:
    routing = project_path / "routing.json"
    if routing.exists():
        try: data = json.loads(routing.read_text(encoding="utf-8"))
        except Exception: data = {}
        provider = str(data.get("force_provider") or "").strip().lower()
        if provider == "openai": return f"OpenAI · {data.get('openai_model') or 'model'}"
        if provider == "claude": return f"Claude · {data.get('claude_model') or 'model'}"
        if provider == "codex": return f"Codex · {data.get('codex_model') or 'model'}"
        if provider: return provider
    provider, model = _active_provider_model()
    if provider and model: return f"{provider.upper()} · {model}"
    return "—"

def _mark_project_done(project_path: Path) -> None:
    done_path = project_path / "DONE.md"
    if not done_path.exists():
        done_path.write_text(f"# DONE\nMarked done at {datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    (project_path / "status.json").write_text(
        json.dumps({"status": "DONE", "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")

def _continue_project_work(project: str, project_path: Path) -> None:
    done_path = project_path / "DONE.md"
    if done_path.exists():
        try: done_path.unlink()
        except Exception: pass
    (project_path / "status.json").write_text(
        json.dumps({"status": "IN_PROGRESS", "timestamp": datetime.now(timezone.utc).isoformat(), "reason": "continue_work"}, indent=2), encoding="utf-8")
    _write_continue_work_override(project, project_path)
    _touch_trigger("continue_work")

def _pick_active_project(projects: list[dict]) -> dict | None:
    if not projects: return None
    def _latest(items):
        return sorted(items, key=lambda p: p.get("last") or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)[0] if items else None
    for st_filter in ("IN_PROGRESS", "PENDING_HUMAN_REVIEW", "ERROR"):
        result = _latest([p for p in projects if p.get("status") == st_filter])
        if result: return result
    return _latest(projects)

def _project_file_count(p: Path) -> int:
    _skip = {"node_modules", ".git", ".next", "__pycache__", ".venv", "venv"}
    count = 0
    try:
        for item in p.iterdir():
            if item.name in _skip: continue
            if item.is_file() and not item.name.startswith("."): count += 1
            elif item.is_dir(): count += sum(1 for f in item.rglob("*") if f.is_file() and not any(s in f.parts for s in _skip))
    except Exception: pass
    return count

def _read_lines_safe(path: Path, max_lines: int = 6) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return [ln for ln in lines if ln.strip()][:max_lines]
    except Exception: return []

def _project_recent_changes(p: Path) -> list[str]:
    changelog = p / "CHANGELOG.md"
    return _read_lines_safe(changelog, 6) if changelog.exists() else []

def _gather_digest_context(days: int = 1) -> str:
    parts: list[str] = []
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
                        if dt < cutoff: break
                    recent_events.append(f"  {_summarize_event(obj)} ({ts})")
                except Exception: continue
        except Exception: pass
        if recent_events: parts.append("RECENT CYCLE EVENTS:\n" + "\n".join(recent_events[:30]))
    router_log = Path("/home/hackerman/agent-runtime/logs/router_events.jsonl")
    if router_log.exists():
        router_items: list[str] = []
        try:
            lines = router_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-100:]):
                try:
                    obj = json.loads(line)
                    router_items.append(f"  {_summarize_event(obj)} ({obj.get('ts', '')})")
                except Exception: continue
        except Exception: pass
        if router_items: parts.append("ROUTER EVENTS:\n" + "\n".join(router_items[:15]))
    inbox_text = read_inbox().strip()
    if inbox_text: parts.append(f"INBOX:\n{inbox_text[:3000]}")
    updates = _recent_updates_global(max_lines=6)
    if updates:
        cl_parts = [f"  [{u['project']}] " + " | ".join(u["lines"][:3]) for u in updates[:4]]
        parts.append("RECENT CHANGELOG ENTRIES:\n" + "\n".join(cl_parts))
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    if projects_root.exists():
        statuses = []
        for p in projects_root.iterdir():
            if p.is_dir():
                sp = p / "status.json"
                if sp.exists():
                    try:
                        data = json.loads(sp.read_text(encoding="utf-8"))
                        statuses.append(f"  {p.name}: {data.get('status', '?')}")
                    except Exception: pass
        if statuses: parts.append("PROJECT STATUSES:\n" + "\n".join(statuses))
    return "\n\n".join(parts) if parts else "(no data available)"

# ── Sidebar ──────────────────────────────────────────────────────
def _render_sidebar() -> None:
    with st.sidebar:
        if LOGO_PATH.exists(): st.image(str(LOGO_PATH), width=48)
        st.markdown(
            '<div style="font-size:0.95rem;font-weight:700;color:var(--accent);margin:-4px 0 2px;">Agent Runtime</div>'
            '<div style="font-size:0.65rem;color:var(--muted);opacity:0.6;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px;">Control Center</div>',
            unsafe_allow_html=True,
        )
        _sb_status, _sb_status_ts = _read_project_status()
        _sb_health, _ = _read_cycle_health()
        _sb_health_label, _ = _cycle_label(_sb_health, _sb_status)
        _sb_hv = "ok" if _sb_health_label == "ok" else ("warn" if _sb_health_label == "warn" else ("error" if _sb_health_label == "error" else "neutral"))
        _sb_sv = "ok" if _sb_status in ("IN_PROGRESS", "DONE") else ("warn" if _sb_status == "PENDING_HUMAN_REVIEW" else "neutral")
        _sb_provider, _ = _active_provider_model()
        _sb_last_cycle = _last_cycle_ts()
        _sb_cycle_str = "—"
        if _sb_last_cycle:
            _sb_age = (datetime.now(timezone.utc) - _sb_last_cycle).total_seconds() / 60.0
            _sb_cycle_str = f"{_sb_age:.0f}m ago" if _sb_age < 60 else f"{_sb_age/60:.1f}h ago"
        _sb_all_files = list_matching(output_patterns())
        _sb_inbox_lines = len([l for l in read_inbox().splitlines() if l.strip()])
        st.markdown(f"""
            <div class="sb-status-card">
                <div class="sb-status-row"><span class="sb-icon">●</span><span class="sb-label">Cycle</span><span class="sb-value {_sb_hv}">{_sb_health_label.upper()}</span></div>
                <div class="sb-status-row"><span class="sb-icon">◉</span><span class="sb-label">Project</span><span class="sb-value {_sb_sv}">{_sb_status}</span></div>
                <div class="sb-status-row"><span class="sb-icon">⏱</span><span class="sb-label">Last</span><span class="sb-value neutral">{_sb_cycle_str}</span></div>
                <div class="sb-status-row"><span class="sb-icon">⚡</span><span class="sb-label">Provider</span><span class="sb-value neutral">{_sb_provider.upper() if _sb_provider else '?'}</span></div>
            </div>""", unsafe_allow_html=True)
        # Wallet balance indicator
        try:
            _sb_sol = fin.get_solana_balance()
            _sb_sol_price = fin.get_sol_price() if _sb_sol else None
            _sb_sol_usd = f"${_sb_sol * _sb_sol_price:.2f}" if (_sb_sol and _sb_sol_price) else "—"
            _sb_sol_str = f"{_sb_sol:.3f}" if _sb_sol is not None else "—"
            st.markdown(f"""
                <div class="sb-status-card" style="margin-top:8px;">
                    <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);opacity:0.55;margin-bottom:6px;">Wallet</div>
                    <div class="sb-status-row"><span class="sb-icon">◎</span><span class="sb-label">SOL</span><span class="sb-value ok">{_sb_sol_str}</span></div>
                    <div class="sb-status-row"><span class="sb-icon">$</span><span class="sb-label">Value</span><span class="sb-value neutral">{_sb_sol_usd}</span></div>
                </div>""", unsafe_allow_html=True)
        except Exception:
            pass
        st.markdown('<div class="sb-section-label">Quick Actions</div>', unsafe_allow_html=True)
        if st.button("🔄  Refresh", key="sidebar_refresh", use_container_width=True): st.rerun()
        if st.button("⚡  Kick cycle", key="sidebar_kick", use_container_width=True):
            _touch_trigger("sidebar_kick"); _set_flash("success", "Cycle triggered."); st.rerun()
        llama_url = "http://127.0.0.1:11434"
        if hasattr(st, "link_button"): st.link_button("🦙  Open Llama", llama_url, use_container_width=True)
        else: st.markdown(f'<a class="sb-link-btn" href="{llama_url}" target="_blank" rel="noopener">🦙  Open Llama</a>', unsafe_allow_html=True)
        marketplace_url = "http://localhost:3000"
        if hasattr(st, "link_button"): st.link_button("🛒  Marketplace", marketplace_url, use_container_width=True)
        else: st.markdown(f'<a class="sb-link-btn" href="{marketplace_url}" target="_blank" rel="noopener">🛒  Marketplace</a>', unsafe_allow_html=True)
        _pin_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/pinned_note.txt")
        _pin_text = ""
        if _pin_path.exists():
            try: _pin_text = _pin_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception: pass
        if _pin_text:
            st.markdown('<div class="sb-section-label">📌 Pinned Note</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="border:1px solid var(--accent-border);border-radius:8px;padding:8px 10px;background:rgba(7,12,7,0.4);font-size:0.78rem;color:var(--text);white-space:pre-wrap;line-height:1.5;">{_html.escape(_pin_text[:200])}</div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-section-label">Stats</div>', unsafe_allow_html=True)
        st.markdown(f"""
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">
                <div style="text-align:center;padding:8px 4px;border-radius:8px;background:rgba(7,12,7,0.4);border:1px solid var(--accent-border);">
                    <div style="font-size:1.1rem;font-weight:700;color:var(--accent);">{len(_sb_all_files)}</div>
                    <div style="font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;">Proposals</div>
                </div>
                <div style="text-align:center;padding:8px 4px;border-radius:8px;background:rgba(7,12,7,0.4);border:1px solid var(--accent-border);">
                    <div style="font-size:1.1rem;font-weight:700;color:var(--accent);">{_sb_inbox_lines}</div>
                    <div style="font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;">Inbox</div>
                </div>
            </div>""", unsafe_allow_html=True)
        st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
        auto_refresh = st.toggle("Auto-refresh (30s)", value=False, key="auto_refresh")
        if auto_refresh: st.caption("⟳ Refreshing every 30s")
        st.markdown(f'<div style="font-size:0.65rem;color:var(--muted);opacity:0.4;margin-top:12px;text-align:center;">{datetime.now(PST).strftime("%H:%M PST")}</div>', unsafe_allow_html=True)

# ── Topbar ───────────────────────────────────────────────────────
_hdr_last_cycle = _last_cycle_ts()
_hdr_uptime = ""
if _hdr_last_cycle:
    _hdr_age_min = (datetime.now(timezone.utc) - _hdr_last_cycle).total_seconds() / 60.0
    _hdr_uptime = f"{_hdr_age_min:.0f}m ago" if _hdr_age_min < 60 else f"{_hdr_age_min/60:.1f}h ago"
_hdr_health, _ = _read_cycle_health()
_hdr_ps, _ = _read_project_status()
_hdr_health_label, _ = _cycle_label(_hdr_health, _hdr_ps)
_hdr_provider, _ = _active_provider_model()
_hdr_hv = _variant_from_health(_hdr_health_label)
_hdr_pv = _variant_from_project_status(_hdr_ps)
_hdr_inbox_count = len([l for l in read_inbox().splitlines() if l.strip()])

_logo_uri = ""
if LOGO_PATH.exists():
    try: _logo_uri = f"data:image/svg+xml;base64,{base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')}"
    except Exception: _logo_uri = ""
_logo_html = (f'<img src="{_logo_uri}" style="width:44px;height:44px;object-fit:contain;border-radius:10px;border:1px solid var(--accent-border);background:rgba(7,12,7,0.35);padding:6px;" />' if _logo_uri
    else '<div style="width:44px;height:44px;border-radius:10px;border:1px solid var(--accent-border);background:rgba(7,12,7,0.35);"></div>')

_topbar = st.container()
with _topbar:
    c_left, c_actions = st.columns([3.2, 1.2], vertical_alignment="center")
    with c_left:
        st.markdown(f"""
            <div class="topbar"><div class="topbar-row">
                <div class="topbar-left">{_logo_html}
                  <div class="topbar-title"><div class="h">Agent Runtime Dashboard</div>
                    <div class="sub">{datetime.now(PST).strftime("%a %b %d, %Y")}</div></div></div>
                <div class="topbar-meta">
                  <span class="meta-chip {_hdr_hv}"><span class="dot"></span><strong>Cycle</strong> {_hdr_health_label.upper()}</span>
                  <span class="meta-chip {_hdr_pv}"><span class="dot"></span><strong>Project</strong> {_html.escape(_hdr_ps)}</span>
                  <span class="meta-chip neutral"><span class="dot"></span><strong>Provider</strong> {_hdr_provider.upper() if _hdr_provider else "—"}</span>
                  <span class="meta-chip neutral"><span class="dot"></span><strong>Inbox</strong> {_hdr_inbox_count}</span>
                  <span class="meta-chip neutral"><span class="dot"></span><strong>Last</strong> {_hdr_uptime or "—"}</span>
                </div>
            </div></div>""", unsafe_allow_html=True)
    with c_actions:
        st.markdown('<div class="topbar-actions">', unsafe_allow_html=True)
        a1, a2, a3 = st.columns(3, gap="small")
        with a1:
            if st.button("Refresh", key="top_refresh", use_container_width=True): st.rerun()
        with a2:
            if st.button("Brief", key="top_brief", use_container_width=True):
                st.session_state["_jump_to_brief"] = True; st.rerun()
        with a3:
            if st.button("Kick", key="top_kick", use_container_width=True):
                _touch_trigger("topbar_kick"); st.success("Cycle triggered."); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
tabs = st.tabs(["⚡ Overview", "💰 Portfolio", "📊 Polymarket", "💬 Telegram", "📁 Projects", "📥 Inbox", "📄 Proposals", "📋 Logs"])
_render_sidebar()

# ═══════════════════════════════════════════════════════════════════
# TAB 0: COMMAND (merges Overview + Settings + Digest)
# ═══════════════════════════════════════════════════════════════════
with tabs[0]:
    _page_context("Command", f"Updated {datetime.now(PST).strftime('%H:%M PST')}")

    # ── Status strip ─────────────────────────────────────────────
    _cmd_health, _cmd_reason = _read_cycle_health()
    _cmd_ps, _ = _read_project_status()
    _cmd_hl, _cmd_hn = _cycle_label(_cmd_health, _cmd_ps)
    _cmd_provider, _cmd_model = _active_provider_model()
    _cmd_last = _last_cycle_ts()
    _cmd_age_str = "—"
    if _cmd_last:
        _cmd_age = (datetime.now(timezone.utc) - _cmd_last).total_seconds() / 60.0
        _cmd_age_str = f"{_cmd_age:.0f}m ago" if _cmd_age < 60 else f"{_cmd_age/60:.1f}h ago"
    _cmd_hv = _variant_from_health(_cmd_hl)
    _cmd_pv = _variant_from_project_status(_cmd_ps)
    _cmd_credit_status, _cmd_credit_note = _credit_snapshot()
    _cmd_cv = "ok" if _cmd_credit_status == "ok" else ("warn" if _cmd_credit_status == "low" else "neutral")

    current_mode = read_mode()
    _mode_v = "ok" if current_mode == "DIRECTED" else "warn"
    st.markdown(f"""
        <div class="data-strip">
            {_chip('Mode: ' + current_mode, _mode_v)}
            {_chip('Cycle: ' + _cmd_hl.upper(), _cmd_hv)}
            {_chip('Project: ' + _cmd_ps, _cmd_pv)}
            {_chip('Provider: ' + _cmd_provider.upper(), 'neutral')}
            {_chip('Model: ' + _cmd_model, 'neutral')}
            {_chip('Last: ' + _cmd_age_str, 'neutral')}
            {_chip('Credits: ' + _cmd_credit_status.upper(), _cmd_cv)}
            {_chip('Gate: ' + ('ON' if approval_gate_enabled() else 'OFF'), 'ok' if approval_gate_enabled() else 'neutral')}
        </div>
        <div style="font-size:0.78rem;color:var(--muted);line-height:1.6;margin-bottom:8px;">
            {_cmd_reason} · Patch: <code>{_latest_patch_name()}</code>{(' · ' + _cmd_hn) if _cmd_hn else ''} · {_cmd_credit_note}
        </div>""", unsafe_allow_html=True)

    # ── Controls row (compact) ────────────────────────────────────
    _ctrl_c1, _ctrl_c2, _ctrl_c3 = st.columns([1, 1, 1])
    with _ctrl_c1:
        mode = st.selectbox("Mode", ["DIRECTED", "AUTONOMOUS"], index=0 if current_mode == "DIRECTED" else 1, key="cmd_mode_sel", label_visibility="collapsed")
        if mode != current_mode:
            write_mode(mode); _set_flash("success", f"Mode → {mode}"); st.rerun()
    with _ctrl_c2:
        if st.button("⚡ Kick cycle", key="cmd_kick", use_container_width=True):
            _touch_trigger("cmd_kick"); _set_flash("success", "Cycle triggered."); st.rerun()
    with _ctrl_c3:
        if st.button("🔄 Trigger run", key="cmd_trigger", use_container_width=True):
            trigger_run(); _set_flash("success", "Run triggered."); st.rerun()

    # ── Project Review ────────────────────────────────────────────
    _cmd_proj_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    _cmd_review_projects = []
    if _cmd_proj_root.exists():
        for _prj in sorted(_cmd_proj_root.iterdir()):
            if not _prj.is_dir(): continue
            _prj_st, _prj_reason = _project_status_summary(_prj)
            if _prj_st in ("PENDING_HUMAN_REVIEW",):
                _cmd_review_projects.append((_prj, _prj_st, _prj_reason))
            elif _prj_st == "IN_PROGRESS":
                # Check if cycle log shows tasks completed (done event)
                _prj_log = Path("/home/hackerman/agent-runtime/logs") / f"{_prj.name}_cycle.jsonl"
                if _prj_log.exists():
                    try:
                        _last_line = [l for l in _prj_log.read_text().strip().splitlines() if l.strip()][-1]
                        _last_ev = json.loads(_last_line)
                        if _last_ev.get("event") == "done" or _last_ev.get("status") == "PENDING_HUMAN_REVIEW":
                            _cmd_review_projects.append((_prj, "NEEDS_REVIEW", _last_ev.get("reason") or "tasks completed"))
                    except Exception: pass

    if _cmd_review_projects:
        st.markdown('<div class="section-header">Project Review</div>', unsafe_allow_html=True)
        for _prj, _prj_st, _prj_reason in _cmd_review_projects:
            _prj_age = _project_last_activity(_prj.name, _prj)
            _prj_age_str = _fmt_time(_prj_age.isoformat()) if _prj_age else "—"
            _prj_badge_v = "warn" if _prj_st in ("PENDING_HUMAN_REVIEW", "NEEDS_REVIEW") else "neutral"
            st.markdown(f"""<div class="glass-card">
                <div class="card-title-row">
                    <div class="title">{_html.escape(_prj.name)}</div>
                    <div class="meta">{_html.escape(_prj_age_str)}</div>
                </div>
                <div class="glass-meta">{_chip(_prj_st.replace('_', ' '), _prj_badge_v)} {_html.escape(_prj_reason)}</div>
            </div>""", unsafe_allow_html=True)
            _prjr1, _prjr2 = st.columns(2)
            with _prjr1:
                if st.button(f"Approve DONE", key=f"cmdrev_done_{_prj.name}"):
                    _mark_project_done(_prj); _set_flash("success", f"Marked {_prj.name} DONE."); st.rerun()
            with _prjr2:
                if st.button(f"Continue work", key=f"cmdrev_cont_{_prj.name}"):
                    _continue_project_work(_prj.name, _prj); _set_flash("warning", f"Set {_prj.name} to IN_PROGRESS."); st.rerun()

    # ── Latest Proposal ──────────────────────────────────────────
    st.markdown('<div class="section-header">Latest Proposal</div>', unsafe_allow_html=True)
    _cmd_all_files = list_matching(output_patterns())
    _cmd_proposals = [p for p in _cmd_all_files if not p.name.startswith("review_")]
    _cmd_latest = _latest_pending(_cmd_proposals)
    if not _cmd_latest:
        st.caption("No pending proposals.")
    else:
        try: _cmd_payload = read_json_file(_cmd_latest)
        except Exception: _cmd_payload = {}
        _cmd_summary = str(_cmd_payload.get("summary") or "").strip()
        _cmd_project = str(_cmd_payload.get("project") or "").strip()
        _cmd_id = str(_cmd_payload.get("proposal_id") or _cmd_latest.stem)
        _cmd_pmode = str(_cmd_payload.get("mode") or "—")
        _cmd_time = _fmt_time(stat_mtime_iso(_cmd_latest))
        _cmd_decision = read_decision(_cmd_latest)

        st.markdown(f"""
            <div class="glass-card">
                <div class="card-title-row">
                    <div class="title">{_html.escape(_cmd_project or _cmd_summary or 'Proposal')}</div>
                    <div class="meta">{_html.escape(_cmd_time)}</div>
                </div>
                <div class="glass-meta">ID: {_html.escape(_cmd_id)} · Mode: {_html.escape(_cmd_pmode)}</div>
                <div class="subtle" style="margin-top:6px;">{_html.escape(_cmd_summary or '—')}</div>
            </div>""", unsafe_allow_html=True)

        # Market synopsis
        _cmd_synopsis = _investor_synopsis(_cmd_payload)
        st.markdown("**Market synopsis**")
        st.markdown("\n".join([
            f"- **What it is:** {_cmd_synopsis.get('what') or '—'}",
            f"- **Why now:** {_cmd_synopsis.get('why') or '—'}",
            f"- **Edge:** {_cmd_synopsis.get('edge') or '—'}",
            f"- **Next step:** {_cmd_synopsis.get('next') or '—'}",
            f"- **Tech notes:** {_cmd_synopsis.get('tech') or '—'}",
        ]))

        # Actions & criteria
        _cmd_actions = _as_list(_cmd_payload.get("suggested_actions"))
        _cmd_success = _as_list(_cmd_payload.get("success_criteria"))
        _cmd_done = _as_list(_cmd_payload.get("definition_of_done"))
        if _cmd_actions:
            st.markdown("**Suggested actions**")
            st.markdown("\n".join([f"- {a}" for a in _cmd_actions]))
        if _cmd_success or _cmd_done:
            st.markdown("**Definition of done**")
            st.markdown("\n".join([f"- {d}" for d in (_cmd_done or _cmd_success)]))

        if _cmd_decision:
            st.caption(f"Decision: {_cmd_decision.get('decision','—')} · {_cmd_decision.get('timestamp','—')}")

        # Approve / Reject
        _cmd_note = st.text_input("Decision note (optional)", key=f"cmd_note_{_cmd_latest.name}", placeholder="Why approve or reject?")
        _cmd_gate = approval_gate_enabled()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Approve", key=f"cmd_approve_{_cmd_latest.name}"):
                try:
                    priority_path = write_priority_from_proposal(_cmd_latest, _cmd_payload, _cmd_note)
                    decision_path = write_decision(_cmd_latest, "APPROVE", note=_cmd_note, extra={"priority_path": str(priority_path)})
                    if not priority_path.exists(): raise RuntimeError("Priority file not created.")
                    if not decision_path.exists(): raise RuntimeError("Decision file not created.")
                    if _cmd_gate: trigger_run(); _set_flash("success", f"Approved and queued. Priority: {priority_path}.")
                    else: _set_flash("success", f"Approved. Priority: {priority_path}.")
                    st.rerun()
                except Exception as exc:
                    _set_flash("error", f"Approval failed: {exc}"); st.rerun()
        with c2:
            if st.button("Reject", key=f"cmd_reject_{_cmd_latest.name}"):
                write_decision(_cmd_latest, "REJECT", note=_cmd_note)
                _set_flash("warning", "Rejected. Decision recorded."); st.rerun()
        if (not _cmd_gate) and _cmd_decision and _cmd_decision.get("priority_path"):
            if st.button("Promote to active", key=f"cmd_promote_{_cmd_latest.name}"):
                promoted = promote_priority(Path(_cmd_decision["priority_path"]))
                trigger_run(); _set_flash("success", f"Promoted: {promoted}"); st.rerun()

    # ── Activity Feed ────────────────────────────────────────────
    _cmd_left, _cmd_right = st.columns([1.2, 1], gap="large")
    with _cmd_left:
        st.markdown('<div class="section-header" style="margin-top:0;">Activity</div>', unsafe_allow_html=True)
        _cmd_act_status, _cmd_act_detail = _agent_activity()
        _cmd_act_label = "CONNECTED" if _cmd_act_status == "active" else ("IDLE" if _cmd_act_status == "idle" else "UNKNOWN")
        _cmd_act_color = "var(--accent)" if _cmd_act_status == "active" else "var(--muted)"
        _cmd_act_pulse = '<span class="pulse"></span>' if _cmd_act_status == "active" else ""
        st.markdown(f'<div style="font-size:0.85rem;margin-bottom:10px;">{_cmd_act_pulse}<span style="color:{_cmd_act_color};font-weight:700;">{_cmd_act_label}</span> — {_cmd_act_detail}</div>', unsafe_allow_html=True)
        feed = _activity_feed(limit=6)
        if feed:
            items_html = []
            for i, item in enumerate(feed):
                dot_class = "" if i == 0 else "dimmed"
                items_html.append(f'<div class="activity-item"><div class="activity-dot {dot_class}"></div><div class="activity-content"><div class="activity-ts">{_fmt_time(item["ts"])}</div><div class="activity-text">{item["summary"]}</div></div></div>')
            st.markdown(f'<div class="activity-timeline">{"".join(items_html)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No recent activity.")

    with _cmd_right:
        st.markdown('<div class="section-header" style="margin-top:0;">Issues</div>', unsafe_allow_html=True)
        failures = _recent_failures(3)
        dismissed = _load_dismissed_errors()
        if failures:
            show_dismissed = st.toggle("Show dismissed", value=False, key="cmd_show_dismissed")
            _any_shown = False
            for line in failures:
                err_id = _error_id(line)
                if (err_id in dismissed) and not show_dismissed: continue
                _any_shown = True
                with st.expander(f"Failure {err_id[:8]}", expanded=False):
                    st.code(line[:400], language="json")
                    label = "Dismiss" if err_id not in dismissed else "Restore"
                    if st.button(label, key=f"cmd_dismiss_{err_id}"):
                        if err_id in dismissed: dismissed.remove(err_id)
                        else: dismissed.add(err_id)
                        _save_dismissed_errors(dismissed); st.rerun()
            if not _any_shown: st.success("All failures dismissed.")
        else:
            st.success("No recent issues — all systems nominal.")

# ═══════════════════════════════════════════════════════════════════
# TAB 4: PROJECTS
# ═══════════════════════════════════════════════════════════════════
with tabs[4]:
    _page_context("Projects", "All workspace projects with status and recent changes.")
    _proj_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    _proj_list = [p for p in _proj_root.iterdir() if p.is_dir()] if _proj_root.exists() else []

    if not _proj_list:
        st.markdown('<div class="empty-state"><div class="empty-icon">📂</div><div class="empty-text">No projects found yet.</div></div>', unsafe_allow_html=True)
    else:
        # Summary stats
        _proj_statuses = {p.name: _project_status_summary(p)[0] for p in _proj_list}
        _proj_active = sum(1 for s in _proj_statuses.values() if s == "IN_PROGRESS")
        _proj_review = sum(1 for s in _proj_statuses.values() if s == "PENDING_HUMAN_REVIEW")
        _proj_done = sum(1 for s in _proj_statuses.values() if s == "DONE")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total", len(_proj_list))
        sc2.metric("Active", _proj_active)
        sc3.metric("Review", _proj_review)
        sc4.metric("Done", _proj_done)

        # Reviews needed
        _proj_review_list = [p for p in _proj_list if _proj_statuses[p.name] == "PENDING_HUMAN_REVIEW"]
        if _proj_review_list:
            st.markdown("**Reviews needed**")
            for p in _proj_review_list:
                status, reason, ts = _project_status_detail(p)
                st.markdown(f"- **{p.name}** · {_html.escape(reason or 'needs decision')} · {_fmt_time(ts) if ts else _fmt_mtime(p)}")
                rc1, rc2 = st.columns(2)
                with rc1:
                    if st.button(f"Approve DONE · {p.name}", key=f"proj_done_{p.name}"):
                        _mark_project_done(p); st.success(f"Marked {p.name} DONE."); st.rerun()
                with rc2:
                    if st.button(f"Continue work · {p.name}", key=f"proj_cont_{p.name}"):
                        _continue_project_work(p.name, p); st.warning(f"Set {p.name} to IN_PROGRESS."); st.rerun()

        # Filter / sort
        _pf1, _pf2, _pf3 = st.columns([2, 2, 1])
        with _pf1: _proj_search = st.text_input("Search projects", key="proj_search", placeholder="Filter by name…")
        with _pf2: _proj_status_filter = st.selectbox("Status filter", ["All", "IN_PROGRESS", "DONE", "PENDING_HUMAN_REVIEW", "UNKNOWN"], key="proj_status_filter")
        with _pf3: _proj_sort = st.selectbox("Sort", ["Recent first", "Name A→Z"], key="proj_sort")

        _proj_filtered = _proj_list[:]
        if _proj_search: _proj_filtered = [p for p in _proj_filtered if _proj_search.lower() in p.name.lower()]
        if _proj_status_filter != "All": _proj_filtered = [p for p in _proj_filtered if _proj_statuses.get(p.name) == _proj_status_filter]
        if _proj_sort == "Name A→Z": _proj_filtered.sort(key=lambda p: p.name.lower())
        else: _proj_filtered.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        st.markdown(f'<div class="section-header">Projects ({len(_proj_filtered)})</div>', unsafe_allow_html=True)
        if not _proj_filtered:
            st.caption("No projects match your filters.")
        else:
            for p in _proj_filtered[:12]:
                status = _proj_statuses.get(p.name, "UNKNOWN")
                _, ts_str = _project_status_summary(p)
                file_count = _project_file_count(p)
                has_changelog = (p / "CHANGELOG.md").exists()
                sv = "ok" if status in ("IN_PROGRESS", "DONE") else ("warn" if status == "PENDING_HUMAN_REVIEW" else "neutral")
                si = {"IN_PROGRESS": "🔄", "DONE": "✅", "PENDING_HUMAN_REVIEW": "⏳"}.get(status, "❓")
                agent_hint = _project_agent_hint(p)

                st.markdown(f"""<div class="glass-card" style="margin-bottom:12px;">
                    <div class="glass-title" style="font-size:1.05rem;">{_html.escape(p.name)}</div>
                    <div style="margin:6px 0 8px;"><span class="status-chip {sv}">{si} {_html.escape(status)}</span></div>
                    <div class="glass-meta">Updated: {_html.escape(_fmt_mtime(p))} · {file_count} files{'  ·  changelog' if has_changelog else ''} · Agent: {_html.escape(agent_hint)}</div>
                </div>""", unsafe_allow_html=True)

            # Detail expanders
            st.markdown('<div class="section-header">Project Details</div>', unsafe_allow_html=True)
            for p in _proj_filtered[:12]:
                status = _proj_statuses.get(p.name, "UNKNOWN")
                changes = _project_recent_changes(p)
                with st.expander(f"**{p.name}** — {status} · {_fmt_mtime(p)}", expanded=False):
                    dc1, dc2 = st.columns([1, 1])
                    with dc1:
                        st.caption(f"Path: `{p}`")
                        st.caption(f"Files: {_project_file_count(p)} · Last modified: {_fmt_mtime(p)}")
                        if (p / "DONE.md").exists(): st.caption("✅ DONE.md present")
                    with dc2:
                        if changes:
                            st.markdown("**Recent changelog**")
                            st.code("\n".join(changes), language="text")
                        else: st.caption("No changelog yet.")
                    if status in ("PENDING_HUMAN_REVIEW", "DONE", "IN_PROGRESS"):
                        ac1, ac2 = st.columns(2)
                        with ac1:
                            if status != "DONE":
                                if st.button("Approve DONE", key=f"projd_done_{p.name}"):
                                    _mark_project_done(p); st.success("Marked DONE"); st.rerun()
                        with ac2:
                            if st.button("Continue work", key=f"projd_cont_{p.name}"):
                                _continue_project_work(p.name, p)
                                _touch_trigger(f"continue_work:{p.name}")
                                st.warning("Set to IN_PROGRESS"); st.rerun()

        # Timeline (collapsible)
        with st.expander("Timeline Charts", expanded=False):
            files = list_matching(output_patterns())
            def _counts_last_days(days: int = 14) -> dict[str, int]:
                today = datetime.now().date()
                counts = {(today - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(days - 1, -1, -1)}
                for p in files:
                    dt = extract_timestamp(p).date().strftime("%Y-%m-%d")
                    if dt in counts: counts[dt] += 1
                return counts

            def _current_streak(counts: dict[str, int]) -> int:
                streak = 0
                for day in reversed(list(counts.keys())):
                    if counts[day] > 0: streak += 1
                    else: break
                return streak

            if not files:
                st.caption("No proposal files yet.")
            else:
                last_14 = _counts_last_days(14)
                total_14 = sum(last_14.values())
                most_active = max(last_14.items(), key=lambda x: x[1])
                streak = _current_streak(last_14)
                tc1, tc2, tc3 = st.columns(3)
                tc1.metric("Total (14d)", total_14)
                tc2.metric("Most active", most_active[0], delta=f"{most_active[1]} proposals")
                tc3.metric("Streak", f"{streak} day(s)")
                st.markdown("**Daily activity (14 days)**")
                st.bar_chart(last_14)

                def _count_by(bucket_fn):
                    counts = {}
                    for p in files:
                        key = bucket_fn(extract_timestamp(p))
                        counts[key] = counts.get(key, 0) + 1
                    return dict(sorted(counts.items()))

                day_counts = _count_by(lambda dt: dt.strftime("%Y-%m-%d"))
                week_counts = _count_by(lambda dt: f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}")
                month_counts = _count_by(lambda dt: dt.strftime("%Y-%m"))
                for title, data in [("Per day", day_counts), ("Per week", week_counts), ("Per month", month_counts)]:
                    st.markdown(f"**{title}**")
                    if data:
                        rows = "\n".join([f"| {k} | {v} |" for k, v in data.items()])
                        st.markdown("| Period | Count |\n|---|---|\n" + rows)

        # Recent updates
        st.divider()
        st.markdown('<div class="section-header">Recent Updates</div>', unsafe_allow_html=True)
        _proj_updates = []
        for p in _proj_list:
            cl = p / "CHANGELOG.md"
            if cl.exists():
                lines = _read_lines_safe(cl, 8)
                if lines: _proj_updates.append({"project": p.name, "mtime": cl.stat().st_mtime, "lines": lines})
        _proj_updates.sort(key=lambda x: x["mtime"], reverse=True)
        if not _proj_updates: st.caption("No recent changelog entries.")
        else:
            for item in _proj_updates[:8]:
                with st.expander(f"**{item['project']}** · {datetime.fromtimestamp(item['mtime'], tz=timezone.utc).astimezone(PST).strftime('%b %d, %H:%M')}", expanded=False):
                    st.code("\n".join(item["lines"]), language="text")

# ═══════════════════════════════════════════════════════════════════
# TAB 5: INBOX
# ═══════════════════════════════════════════════════════════════════
with tabs[5]:
    _page_context("Inbox", "Agent directives and priorities — edit and save to guide the next cycle.")
    _inbox_raw = read_inbox()
    _inbox_lines = [l for l in _inbox_raw.splitlines() if l.strip()]
    _inbox_count = len(_inbox_lines)
    _inbox_chars = len(_inbox_raw)
    _inbox_has_urgent = any(_inbox_is_urgent(l) for l in _inbox_lines)

    _inbox_edit_col, _inbox_side_col = st.columns([2, 1], gap="large")
    with _inbox_edit_col:
        if st.session_state.get("_inbox_cleanup_pending") is not None:
            st.session_state["inbox_editor"] = st.session_state.pop("_inbox_cleanup_pending")
        st.markdown(f"""
            <div class="inbox-shell">
              <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;">
                <div style="display:flex;flex-wrap:wrap;gap:10px;">
                  <span class="pill"><strong>{_inbox_count}</strong>&nbsp;directives</span>
                  <span class="pill"><strong>{_inbox_chars:,}</strong>&nbsp;chars</span>
                  {f'<span class="pill urgent"><strong>⚠ Urgent</strong>&nbsp;items detected</span>' if _inbox_has_urgent else '<span class="pill"><strong>OK</strong>&nbsp;no urgent markers</span>'}
                </div>
                <div class="hint">One directive per line. Saved directives are read before each cycle.</div>
              </div>
            </div>""", unsafe_allow_html=True)
        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
        inbox = st.text_area("Inbox directives", value=_inbox_raw, height=460, key="inbox_editor",
            placeholder="Example:\nURGENT: Fix failing health probe\nImprove filtering by project\nAdd clearer call-to-action", label_visibility="collapsed")
        _ib1, _ib2, _ib3 = st.columns([1, 1, 2.2], gap="small")
        with _ib1:
            if st.button("💾 Save directives", key="save_inbox", use_container_width=True):
                write_inbox(inbox); st.success("Saved. Next cycle will use these directives.")
        with _ib2:
            if st.button("↩ Reload from disk", key="reload_inbox", use_container_width=True): st.rerun()
        with _ib3:
            if st.button("🧹 Clean up whitespace", key="cleanup_inbox", use_container_width=True):
                cleaned = "\n".join([ln.rstrip() for ln in inbox.splitlines()]).strip() + ("\n" if inbox.strip() else "")
                st.session_state["_inbox_cleanup_pending"] = cleaned; st.rerun()

    with _inbox_side_col:
        st.markdown('<div class="section-header" style="margin-top:0;font-size:0.95rem;">Preview</div>', unsafe_allow_html=True)
        _preview_lines = [l for l in inbox.splitlines() if l.strip()]
        if _preview_lines:
            _preview_html = []
            for _pl in _preview_lines[:20]:
                _urg = _inbox_is_urgent(_pl)
                _preview_html.append(f'<div class="inbox-line"><span class="inbox-dot {"urgent" if _urg else ""}"></span><span class="inbox-text">{_html.escape(_pl.strip())}</span></div>')
            st.markdown(f'<div class="inbox-preview">{"".join(_preview_html)}</div>', unsafe_allow_html=True)
            if len(_preview_lines) > 20: st.caption(f"…and {len(_preview_lines) - 20} more")
        else:
            st.markdown('<div class="inbox-preview"><div class="inbox-empty">Inbox is empty. Add directives to guide the agent.</div></div>', unsafe_allow_html=True)
        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
        st.markdown("""
            <div class="inbox-help-card"><h4>Writing good directives</h4><div class="subtle">
              <div style="margin-bottom:8px;">Keep each line atomic and testable. Prefer outcomes over vague intent.</div>
              <div class="kv-grid" style="margin:0;">
                <span class="kv-key">Use</span><span class="kv-val">"Add a Health probe summary card"</span>
                <span class="kv-key">Avoid</span><span class="kv-val warn">"Fix health tab"</span>
                <span class="kv-key">Urgent marker</span><span class="kv-val error">URGENT: ...</span>
              </div></div></div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 6: PROPOSALS
# ═══════════════════════════════════════════════════════════════════
with tabs[6]:
    _page_context("Proposals", "Browse proposals and reviews with search, filtering, and detail view.")
    all_files = list_matching(output_patterns())

    def _summarize_output(p: Path) -> dict[str, str]:
        try:
            data = read_json_file(p)
            return {"summary": str(data.get("summary", "")).strip(), "proposal_id": str(data.get("proposal_id", "")).strip(), "mode": str(data.get("mode", "")).strip()}
        except Exception: return {"summary": "", "proposal_id": "", "mode": ""}

    def _clean_label(p: Path, meta: dict[str, str]) -> str:
        stamp = extract_timestamp(p).strftime("%Y-%m-%d %H:%M")
        kind = "Claude" if p.name.startswith("claude_") else "Review"
        short_id = meta.get("proposal_id", "")
        if short_id:
            short_id = short_id.replace("prop-", "").replace("proposal-", "").replace("review_", "").replace("__by_openai", "")[:24]
            return f"{kind} · {stamp} · {short_id}"
        return f"{kind} · {stamp}"

    query = st.text_input("Search", help="Filter by filename...", key="prop_search")
    sort_order = st.selectbox("Sort by", ["Newest first", "Oldest first", "Filename A→Z"], key="prop_sort")
    max_items = st.slider("Max items", min_value=5, max_value=100, value=20, step=5, key="prop_max")
    show_decided = st.checkbox("Show decided proposals", value=True, key="prop_show_decided")

    def _filter_decided(items):
        if show_decided: return items
        return [p for p in items if p.name.startswith("review_") or not _is_decided(p)]

    filtered = [p for p in all_files if query.lower() in p.name.lower()] if query else list(all_files)
    filtered = _filter_decided(filtered)
    visible_all = _filter_decided(list(all_files))

    if not filtered:
        st.markdown('<div class="empty-state"><div class="empty-icon">📄</div><div class="empty-text">No matching proposal files found.</div></div>', unsafe_allow_html=True)
    else:
        claude_files = [p for p in visible_all if p.name.startswith("claude_")]
        review_files = [p for p in visible_all if p.name.startswith("review_")]
        latest_any = _latest_file(visible_all)
        latest_review = _latest_file(review_files)

        if sort_order == "Oldest first": filtered_sorted = sorted(filtered, key=extract_timestamp)
        elif sort_order == "Filename A→Z": filtered_sorted = sorted(filtered, key=lambda p: p.name.lower())
        else: filtered_sorted = sorted(filtered, key=extract_timestamp, reverse=True)

        left_col, right_col = st.columns([1.05, 1.5], gap="large")
        with left_col:
            stats_cols = st.columns(3)
            stats_cols[0].metric("Total", len(visible_all))
            stats_cols[1].metric("Claude", len(claude_files))
            stats_cols[2].metric("Reviews", len(review_files))
            st.caption(f"Latest: {_fmt_time(stat_mtime_iso(latest_any)) if latest_any else '—'} · Review: {_fmt_time(stat_mtime_iso(latest_review)) if latest_review else '—'}")

            label_map = {}; meta_map = {}; options = []
            for p in filtered_sorted[:max_items]:
                meta = _summarize_output(p)
                key = str(p); meta_map[key] = meta; label_map[key] = _clean_label(p, meta); options.append(key)

            if "selected_output" not in st.session_state and options:
                st.session_state["selected_output"] = options[0]
            if options:
                selected = st.radio("Select an output", options=options,
                    index=options.index(st.session_state.get("selected_output", options[0])) if st.session_state.get("selected_output", options[0]) in options else 0,
                    format_func=lambda key: label_map.get(key, key), label_visibility="collapsed", key="prop_radio")
                st.session_state["selected_output"] = selected
                st.caption(f"Showing {min(len(options), max_items)} of {len(filtered)} files.")

        with right_col:
            sel = st.session_state.get("selected_output")
            if not sel: st.info("Select an output to view details.")
            else:
                p = Path(sel)
                meta = _summarize_output(p)
                if p.name.startswith("review_"): kind = "Review"
                elif p.name.startswith("openai_"): kind = "OpenAI proposal"
                elif p.name.startswith("codex_"): kind = "Codex proposal"
                elif p.name.startswith("proposal_"): kind = "Proposal"
                else: kind = "Claude proposal"
                st.markdown(f"""
                    <div class="glass-card">
                        <div class="glass-title">{p.name}</div>
                        <div class="glass-meta">{kind} · {_fmt_time(stat_mtime_iso(p))} · {p.stat().st_size:,} bytes</div>
                        <div class="glass-meta">Mode: {meta.get('mode') or '—'} · ID: {meta.get('proposal_id') or '—'}</div>
                        <div class="glass-meta">{meta.get('summary') or 'No summary.'}</div>
                    </div>""", unsafe_allow_html=True)

                try:
                    payload = read_json_file(p)
                    decision = read_decision(p)
                    is_proposal = not p.name.startswith("review_")

                    if is_proposal and isinstance(payload, dict):
                        # Market synopsis
                        synopsis = _investor_synopsis(payload)
                        st.markdown("**Market synopsis**")
                        st.markdown("\n".join([
                            f"- **What it is:** {synopsis.get('what') or '—'}",
                            f"- **Why now:** {synopsis.get('why') or '—'}",
                            f"- **Edge:** {synopsis.get('edge') or '—'}",
                            f"- **Next step:** {synopsis.get('next') or '—'}",
                            f"- **Tech notes:** {synopsis.get('tech') or '—'}",
                        ]))
                        if payload.get("project"): st.caption(f"Project: {payload.get('project')}")
                        proposal_text = _proposal_text(payload)
                        if proposal_text:
                            with st.expander("Full proposal text", expanded=False):
                                st.text(proposal_text)
                        if payload.get("context"):
                            st.markdown("**Context**")
                            st.caption(payload.get("context") or "—")
                        actions = _as_list(payload.get("suggested_actions"))
                        success = _as_list(payload.get("success_criteria"))
                        done_items = _as_list(payload.get("definition_of_done"))
                        if actions:
                            st.markdown("**Suggested actions**")
                            st.markdown("\n".join([f"- {item}" for item in actions]))
                        if success or done_items:
                            st.markdown("**Definition of done**")
                            st.markdown("\n".join([f"- {item}" for item in (done_items or success)]))
                        conf = payload.get("confidence")
                        if conf is not None: st.caption(f"Confidence: {conf}")

                    if decision:
                        st.markdown("**Decision**")
                        st.markdown(f"- Status: **{decision.get('decision','—')}**\n- Time: {decision.get('timestamp','—')}\n- Note: {decision.get('note') or '—'}")
                        if decision.get("priority_path"): st.caption(f"Priority: `{decision.get('priority_path')}`")

                    if is_proposal and isinstance(payload, dict):
                        st.markdown("**Approval**")
                        _gate_on = approval_gate_enabled()
                        note = st.text_input("Decision note", key=f"prop_note_{p.name}", placeholder="Why approve or reject?")
                        bc1, bc2, bc3 = st.columns(3)
                        with bc1:
                            if st.button("Approve", key=f"prop_approve_{p.name}"):
                                try:
                                    priority_path = write_priority_from_proposal(p, payload, note)
                                    decision_path = write_decision(p, "APPROVE", note=note, extra={"priority_path": str(priority_path)})
                                    if not priority_path.exists(): raise RuntimeError("Priority not created.")
                                    if not decision_path.exists(): raise RuntimeError("Decision not created.")
                                    if _gate_on: trigger_run(); _set_flash("success", f"Approved and queued.")
                                    else: _set_flash("success", f"Approved. Priority: {priority_path}.")
                                    st.rerun()
                                except Exception as exc: _set_flash("error", f"Failed: {exc}"); st.rerun()
                        with bc2:
                            if st.button("Reject", key=f"prop_reject_{p.name}"):
                                write_decision(p, "REJECT", note=note)
                                _set_flash("warning", "Rejected."); st.rerun()
                        with bc3:
                            if (not _gate_on) and decision and decision.get("priority_path"):
                                if st.button("Promote", key=f"prop_promote_{p.name}"):
                                    promoted = promote_priority(Path(decision["priority_path"]))
                                    trigger_run(); _set_flash("success", f"Promoted: {promoted}"); st.rerun()

                    st.json(payload)
                    st.download_button("Download JSON", data=json.dumps(payload, indent=2), file_name=p.name, mime="application/json", key=f"prop_dl_{p.name}")
                except Exception as e:
                    st.error(f"Failed to read JSON: {e}")
                    st.code(p.read_text(encoding="utf-8")[:12000])

# ═══════════════════════════════════════════════════════════════════
# TAB 7: LOGS
# ═══════════════════════════════════════════════════════════════════
with tabs[7]:
    _page_context("Logs & Health", "System health, patch metrics, and log browser.")

    # ── Health Summary ───────────────────────────────────────────
    st.markdown('<div class="section-header">Health Summary</div>', unsafe_allow_html=True)
    cycle_log = Path("/home/hackerman/agent-runtime/logs/dashboard_cycle.jsonl")

    def _parse_cycle_events(limit: int = 500) -> list[dict]:
        if not cycle_log.exists(): return []
        events = []
        try:
            lines = cycle_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in reversed(lines[-limit:]):
                try: events.append(json.loads(line))
                except Exception: pass
        except Exception: pass
        return events

    cycle_events = _parse_cycle_events(500)
    autopatch_events = [e for e in cycle_events if e.get("event") == "autopatch"]
    successes = [e for e in autopatch_events if e.get("returncode") == 0]
    failures_list = [e for e in autopatch_events if e.get("returncode") != 0]
    total_patches = len(autopatch_events)
    success_count = len(successes)
    fail_count = len(failures_list)
    success_rate = (success_count / total_patches * 100) if total_patches else 0

    hc1, hc2, hc3, hc4 = st.columns(4)
    hc1.metric("Total patches", total_patches)
    hc2.metric("Succeeded", success_count)
    hc3.metric("Failed", fail_count)
    hc4.metric("Success rate", f"{success_rate:.0f}%")

    # Cycle frequency
    cycle_starts = [e for e in cycle_events if e.get("event") == "cycle_start"]
    def _ts_dt_log(obj):
        ts = obj.get("ts", "")
        if not ts: return None
        try: return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception: return None

    if cycle_starts:
        recent_starts = [dt for cs in cycle_starts[:50] if (dt := _ts_dt_log(cs))]
        if len(recent_starts) >= 2:
            recent_starts.sort()
            gaps = [(recent_starts[i+1] - recent_starts[i]).total_seconds() / 60.0 for i in range(len(recent_starts) - 1)]
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Avg interval", f"{sum(gaps)/len(gaps):.1f} min")
            fc2.metric("Min interval", f"{min(gaps):.1f} min")
            fc3.metric("Max interval", f"{max(gaps):.1f} min")

    # Daily outcomes chart
    st.markdown("**Daily patch outcomes (14 days)**")
    today = datetime.now(timezone.utc).date()
    day_labels = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    day_ok = {d: 0 for d in day_labels}
    day_fail = {d: 0 for d in day_labels}
    for e in autopatch_events:
        dt = _ts_dt_log(e)
        if not dt: continue
        d = dt.date().isoformat()
        if d in day_ok:
            if e.get("returncode") == 0: day_ok[d] += 1
            else: day_fail[d] += 1
    import pandas as pd
    st.bar_chart(pd.DataFrame({"Succeeded": day_ok, "Failed": day_fail}))

    # Recent failures
    if failures_list:
        with st.expander(f"Recent failures ({len(failures_list[:5])})", expanded=False):
            for evt in failures_list[:5]:
                ts = evt.get("ts", ""); rc = evt.get("returncode", "?"); stderr = evt.get("stderr", "")[:300]
                with st.expander(f"{_fmt_time(ts)} · rc={rc}", expanded=False):
                    st.json(evt)
                    if stderr: st.code(stderr, language="text")

    # ── Log Browser ──────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-header">Log Browser</div>', unsafe_allow_html=True)
    logs_dir = Path("/home/hackerman/agent-runtime/logs")

    def _list_log_files(directory, max_files=50):
        if not directory.exists(): return []
        log_files = []
        for ext in ("*.jsonl", "*.log", "*.txt", "*.diff"): log_files.extend(directory.glob(ext))
        return sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]

    def _tail_file(path, max_lines=100):
        try: return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
        except Exception as e: return f"(error: {e})"

    def _parse_jsonl_entries(path, max_entries=50):
        entries = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines[-200:]):
                line = line.strip()
                if not line: continue
                try: entries.append(json.loads(line))
                except json.JSONDecodeError: entries.append({"_raw": line})
                if len(entries) >= max_entries: break
        except Exception: pass
        return entries

    if not logs_dir.exists():
        st.warning(f"Logs directory not found: {logs_dir}")
    else:
        log_files = _list_log_files(logs_dir)
        if not log_files: st.info("No log files found.")
        else:
            lf1, lf2 = st.columns([3, 1])
            with lf1:
                selected_log = st.selectbox("Log file", log_files,
                    format_func=lambda p: f"{p.name}  ({_fmt_mtime(p)}, {p.stat().st_size:,} bytes)", key="log_file_select")
            with lf2:
                tail_lines = st.number_input("Tail lines", min_value=10, max_value=500, value=80, step=10, key="log_tail")
            if selected_log:
                st.caption(f"Last {tail_lines} lines of **{selected_log.name}**")
                if selected_log.suffix == ".jsonl":
                    view_mode = st.radio("View", ["Structured", "Raw"], horizontal=True, key="log_view_mode")
                    if view_mode == "Structured":
                        entries = _parse_jsonl_entries(selected_log, max_entries=tail_lines)
                        if not entries: st.info("No entries.")
                        else:
                            for i, entry in enumerate(entries[:40]):
                                if "_raw" in entry: st.code(entry["_raw"], language="text")
                                else:
                                    event = entry.get("event", ""); ts = entry.get("timestamp", entry.get("ts", "")); rc = entry.get("returncode", "")
                                    label = f"{_fmt_time(ts) if ts else '—'} · {event}" + (f" · rc={rc}" if rc != "" else "")
                                    with st.expander(label, expanded=(i == 0)): st.json(entry)
                    else: st.code(_tail_file(selected_log, max_lines=tail_lines), language="json")
                elif selected_log.suffix == ".diff": st.code(_tail_file(selected_log, max_lines=tail_lines), language="diff")
                else: st.code(_tail_file(selected_log, max_lines=tail_lines), language="text")
                if st.button("Refresh", key="log_refresh"): st.rerun()

    # ── Governor Audit (collapsible) ─────────────────────────────
    with st.expander("Governor Audit Log", expanded=False):
        _gov_audit_path = Path("/home/hackerman/agent-runtime/logs/governor_audit.jsonl")
        if _gov_audit_path.exists():
            _gov_lines = []
            try:
                for _gl in reversed(_gov_audit_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]):
                    try: _gov_lines.append(json.loads(_gl))
                    except Exception: continue
            except Exception: pass
            if _gov_lines:
                _blocked = [e for e in _gov_lines if not e.get("ok", True)]
                _passed = [e for e in _gov_lines if e.get("ok", True)]
                gc1, gc2, gc3 = st.columns(3)
                gc1.metric("Recent checks", len(_gov_lines))
                gc2.metric("Passed", len(_passed))
                gc3.metric("Blocked", len(_blocked))
                if _blocked:
                    st.markdown("**Blocked actions:**")
                    for _be in _blocked[:5]:
                        with st.expander(f"{_fmt_time(_be.get('ts','?'))} · {_be.get('check','?')}: {', '.join(_be.get('reasons',['?']))}", expanded=False):
                            st.json(_be)
            else: st.caption("No governor audit entries yet.")
        else: st.caption("Governor audit log not found.")

    # ── UI Watch (collapsible) ───────────────────────────────────
    with st.expander("UI Watch (Playwright)", expanded=False):
        ui_status_path = Path("/home/hackerman/agent-runtime/logs/ui_watch/latest_status.json")
        if not ui_status_path.exists(): st.warning("UI Watch status not found.")
        else:
            try: ui_status = json.loads(ui_status_path.read_text(encoding="utf-8"))
            except Exception: ui_status = {}
            checks = ui_status.get("checks", [])
            if ui_status.get("ok"): st.success("All watched UIs are healthy.")
            else: st.error("One or more watched UIs are failing.")
            for entry in checks:
                url = entry.get("url", "unknown"); ok = entry.get("ok", False)
                title = entry.get("title", ""); label = f"{url} · {title}" if title else url
                if ok: st.success(label)
                else:
                    st.error(label)
                    errs = entry.get("errors", [])
                    if errs: st.caption("; ".join(errs[:3]))

# ═══════════════════════════════════════════════════════════════════
# TAB 1: PORTFOLIO
# ═══════════════════════════════════════════════════════════════════
with tabs[1]:
    _page_context("Portfolio", f"Updated {datetime.now(PST).strftime('%H:%M PST')}")

    # ── Fetch data (cached for this render) ───────────────────────
    @st.cache_data(ttl=30)
    def _fetch_portfolio():
        try:
            return fin.compute_portfolio_snapshot()
        except Exception:
            return fin.get_cached_portfolio() or {}

    _pf = _fetch_portfolio()
    _pf_total = _pf.get("total_value_usd", 0)
    _pf_holdings = _pf.get("holdings", [])
    _pf_policy = _pf.get("policy", {})
    try:
        _pf_change = fin.get_portfolio_24h_change()
    except Exception:
        _pf_change = {"change_usd": 0, "change_pct": 0}

    # ── 1. COMMAND CENTER ─────────────────────────────────────────
    # Determine agent status
    _agent_status = "live"
    _agent_label = "OPERATIONAL"
    _pol_mode = _pf_policy.get("mode", "?")
    if _pol_mode not in ("LIVE", "DRY_RUN"):
        _agent_status = "error"
        _agent_label = "OFFLINE"
    elif _pf_policy.get("daily_remaining_usd", 999) <= 0:
        _agent_status = "idle"
        _agent_label = "LIMIT REACHED"

    _pf_pct = _pf_change.get("change_pct", 0)
    _pf_delta = _pf_change.get("change_usd", 0)
    _pf_delta_cls = "up" if _pf_delta >= 0 else "down"
    _daily_spent = _pf_policy.get("daily_spent_usd", 0)
    _daily_max = _pf_policy.get("max_daily_usd", 25)
    _daily_pct = (_daily_spent / _daily_max * 100) if _daily_max > 0 else 0
    _tx_count = _pf_policy.get("daily_tx_count", 0)
    _tx_max = _pf_policy.get("max_daily_txs", 5)

    try:
        _all_events = fin.get_financial_events(limit=200)
    except Exception:
        _all_events = []
    _trade_count = sum(1 for e in _all_events if e.get("event") in ("trade", "swap", "bet"))

    st.markdown(f'''<div class="cmd-center">
        <div class="cmd-row">
            <div class="cmd-status">
                <div class="pulse-dot {_agent_status}"></div>
                <span class="status-label {_agent_status}">{_agent_label}</span>
            </div>
            <div class="cmd-divider"></div>
            <div class="cmd-metrics">
                <div class="cmd-metric">
                    <div class="val">${_pf_total:.2f}</div>
                    <div class="lbl">Portfolio</div>
                </div>
                <div class="cmd-metric">
                    <div class="val {_pf_delta_cls}">{_pf_pct:+.1f}%</div>
                    <div class="lbl">24h Change</div>
                </div>
                <div class="cmd-metric">
                    <div class="val">{len(_pf_holdings)}</div>
                    <div class="lbl">Assets</div>
                </div>
                <div class="cmd-metric">
                    <div class="val">{_tx_count}/{_tx_max}</div>
                    <div class="lbl">Tx Today</div>
                </div>
                <div class="cmd-metric">
                    <div class="val">{_daily_pct:.0f}%</div>
                    <div class="lbl">Budget Used</div>
                </div>
                <div class="cmd-metric">
                    <div class="val">{_trade_count}</div>
                    <div class="lbl">All Trades</div>
                </div>
            </div>
        </div>
    </div>''', unsafe_allow_html=True)

    # ── 2. ALERTS & NOTIFICATIONS ─────────────────────────────────
    _alerts: list[dict] = []
    # Check low balance
    _sol_bal = _pf.get("sol_balance")
    if _sol_bal is not None and _sol_bal < 0.01:
        _alerts.append({"level": "critical", "icon": "\U0001f6a8", "title": "SOL balance critically low", "detail": f"Only {_sol_bal:.4f} SOL remaining. Fund wallet to continue operations.", "ts": ""})
    elif _sol_bal is not None and _sol_bal < 0.05:
        _alerts.append({"level": "warning", "icon": "\u26a0\ufe0f", "title": "SOL balance running low", "detail": f"{_sol_bal:.4f} SOL remaining. Consider adding funds soon.", "ts": ""})
    # Check daily budget
    if _daily_pct >= 100:
        _alerts.append({"level": "critical", "icon": "\U0001f6d1", "title": "Daily budget exhausted", "detail": f"${_daily_spent:.2f} / ${_daily_max:.2f} spent. No more transactions until reset.", "ts": ""})
    elif _daily_pct >= 80:
        _alerts.append({"level": "warning", "icon": "\U0001f4b8", "title": "Approaching daily limit", "detail": f"${_daily_spent:.2f} / ${_daily_max:.2f} ({_daily_pct:.0f}%) of daily budget used.", "ts": ""})
    # Check policy mode
    if _pol_mode not in ("LIVE", "DRY_RUN"):
        _alerts.append({"level": "critical", "icon": "\u2699\ufe0f", "title": "Policy mode unknown", "detail": f"Mode is '{_pol_mode}'. Check policy.yaml configuration.", "ts": ""})
    # Check recent alerts from alerts.jsonl
    try:
        _recent_alerts = fin._read_jsonl(fin.ALERTS_LOG, limit=5)
        for _ra in _recent_alerts[-3:]:
            _alerts.append({"level": "info", "icon": "\U0001f4e1", "title": _ra.get("alert", "Alert"), "detail": _ra.get("message", "")[:200], "ts": _ra.get("ts", "")[:16]})
    except Exception:
        pass
    # Check for new Telegram messages (unread)
    try:
        _tg_inbox = fin.read_telegram_inbox(limit=5)
        _tg_outbox_count = len(fin._read_jsonl(fin.TELEGRAM_MESSAGES_OUT, limit=100))
        _tg_inbox_count = len(fin._read_jsonl(fin.TELEGRAM_MESSAGES_IN, limit=100))
        _unread = _tg_inbox_count - _tg_outbox_count
        if _unread > 0:
            _alerts.append({"level": "info", "icon": "\U0001f4ac", "title": f"{_unread} new Telegram message{'s' if _unread > 1 else ''}", "detail": f"Latest: {_tg_inbox[-1].get('message', '')[:80]}..." if _tg_inbox else "", "ts": _tg_inbox[-1].get("ts", "")[:16] if _tg_inbox else ""})
    except Exception:
        pass

    if _alerts:
        st.markdown(f'<div class="section-header">Alerts ({len(_alerts)})</div>', unsafe_allow_html=True)
        for _al in _alerts:
            _al_ts_html = f'<div class="alert-ts">{_html.escape(_al["ts"])}</div>' if _al.get("ts") else ""
            st.markdown(f'<div class="alert-card {_al["level"]}"><div class="alert-icon">{_al["icon"]}</div><div class="alert-body"><div class="alert-title">{_html.escape(_al["title"])}</div><div class="alert-detail">{_html.escape(_al["detail"])}</div>{_al_ts_html}</div></div>', unsafe_allow_html=True)

    # ── 3. WALLET BALANCES ────────────────────────────────────────
    st.markdown('<div class="section-header">Wallet Balances</div>', unsafe_allow_html=True)
    w1, w2, w3 = st.columns(3)
    with w1:
        _sol_addr = fin.get_solana_address()
        _sol_price = _pf.get("sol_price")
        _sol_val = (_sol_bal or 0) * (_sol_price or 0)
        st.markdown(f"""<div class="pos-card">
            <div class="pos-header">
                <span class="pos-sym">\u25ce SOL</span>
                <span class="pos-chain">SOLANA</span>
            </div>
            <div class="pos-metrics">
                <span class="pm-label">Address</span><span class="pm-val" style="font-size:0.68rem;word-break:break-all;">{_html.escape((_sol_addr[:12] + '...' + _sol_addr[-6:]) if len(_sol_addr) > 18 else (_sol_addr or '\u2014'))}</span>
                <span class="pm-label">Balance</span><span class="pm-val up">{f'{_sol_bal:.4f}' if _sol_bal is not None else '\u2014'}</span>
                <span class="pm-label">Price</span><span class="pm-val">{f'${_sol_price:.2f}' if _sol_price else '\u2014'}</span>
            </div>
            <div class="pos-pnl">
                <div class="pnl-val up">${_sol_val:.2f}</div>
                <div class="pnl-label">Value</div>
            </div>
        </div>""", unsafe_allow_html=True)
    with w2:
        _base_addr = fin.get_base_address()
        _base_bal = _pf.get("base_balance")
        _eth_price = _pf.get("eth_price")
        _base_val = (_base_bal or 0) * (_eth_price or 0)
        st.markdown(f"""<div class="pos-card">
            <div class="pos-header">
                <span class="pos-sym">\u2b21 ETH</span>
                <span class="pos-chain">BASE</span>
            </div>
            <div class="pos-metrics">
                <span class="pm-label">Address</span><span class="pm-val" style="font-size:0.68rem;word-break:break-all;">{_html.escape((_base_addr[:12] + '...' + _base_addr[-6:]) if len(_base_addr) > 18 else (_base_addr or '\u2014'))}</span>
                <span class="pm-label">Balance</span><span class="pm-val{' up' if _base_bal else ''}">{f'{_base_bal:.6f}' if _base_bal is not None else '\u2014'}</span>
                <span class="pm-label">Price</span><span class="pm-val">{f'${_eth_price:.2f}' if _eth_price else '\u2014'}</span>
            </div>
            <div class="pos-pnl">
                <div class="pnl-val{' up' if _base_val > 0 else ''}">${_base_val:.2f}</div>
                <div class="pnl-label">Value</div>
            </div>
        </div>""", unsafe_allow_html=True)
    with w3:
        _poly_addr = fin.get_base_address()  # Same EVM key
        _poly_usdc = _pf.get("poly_usdc_balance") or 0
        _poly_matic = _pf.get("poly_matic_balance") or 0
        # Sum USDC.e + MATIC value from holdings
        _poly_val = _poly_usdc
        for _h in _pf_holdings:
            if _h.get("chain") == "polygon" and _h.get("symbol") == "MATIC":
                _poly_val += _h.get("value_usd", 0)
                break
        st.markdown(f"""<div class="pos-card">
            <div class="pos-header">
                <span class="pos-sym">\U0001f4b2 USDC.e</span>
                <span class="pos-chain">POLYMARKET</span>
            </div>
            <div class="pos-metrics">
                <span class="pm-label">Address</span><span class="pm-val" style="font-size:0.68rem;word-break:break-all;">{_html.escape((_poly_addr[:12] + '...' + _poly_addr[-6:]) if len(_poly_addr) > 18 else (_poly_addr or '\u2014'))}</span>
                <span class="pm-label">USDC.e</span><span class="pm-val up">${_poly_usdc:.2f}</span>
                <span class="pm-label">MATIC</span><span class="pm-val">{_poly_matic:.2f} (gas)</span>
            </div>
            <div class="pos-pnl">
                <div class="pnl-val up">${_poly_val:.2f}</div>
                <div class="pnl-label">Polymarket Funds</div>
            </div>
        </div>""", unsafe_allow_html=True)

    # ── 4. POSITION CARDS (enhanced with sparklines) ──────────────
    if _pf_holdings:
        st.markdown(f'<div class="section-header">Holdings ({len(_pf_holdings)})</div>', unsafe_allow_html=True)
        _pos_cols = st.columns(min(len(_pf_holdings), 3))
        for _idx, _h in enumerate(_pf_holdings):
            with _pos_cols[_idx % min(len(_pf_holdings), 3)]:
                _h_sym = _html.escape(str(_h.get("symbol", "?")))
                _h_chain = _html.escape(str(_h.get("chain", "?")))
                _h_amt = _h.get("amount", 0)
                _h_price = _h.get("price_usd", 0)
                _h_val = _h.get("value_usd", 0)
                _h_pct = (_h_val / _pf_total * 100) if _pf_total > 0 else 0
                _h_pct_cls = "up" if _h_pct > 0 else ""
                st.markdown(f"""<div class="pos-card">
                    <div class="pos-header">
                        <span class="pos-sym">{_h_sym}</span>
                        <span class="pos-chain">{_h_chain}</span>
                    </div>
                    <div class="pos-metrics">
                        <span class="pm-label">Amount</span><span class="pm-val">{_h_amt:.4f}</span>
                        <span class="pm-label">Price</span><span class="pm-val">${_h_price:.4f}</span>
                        <span class="pm-label">Weight</span><span class="pm-val {_h_pct_cls}">{_h_pct:.1f}%</span>
                    </div>
                    <div class="pos-pnl">
                        <div class="pnl-val up">${_h_val:.2f}</div>
                        <div class="pnl-label">Value</div>
                    </div>
                </div>""", unsafe_allow_html=True)
                # Mini sparkline via Plotly if we have price history
                try:
                    _hist = fin.get_portfolio_history(limit=24)
                    if len(_hist) >= 2:
                        import plotly.graph_objects as go
                        _prices = [h.get("total_value_usd", 0) for h in _hist]
                        _spark_color = "#39ff14" if _prices[-1] >= _prices[0] else "#ff5c5c"
                        fig = go.Figure(go.Scatter(
                            y=_prices, mode='lines',
                            line=dict(color=_spark_color, width=2),
                            fill='tozeroy',
                            fillcolor=f"rgba({','.join(str(int(_spark_color.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))},0.08)",
                        ))
                        fig.update_layout(
                            height=60, margin=dict(l=0, r=0, t=0, b=0),
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(visible=False), yaxis=dict(visible=False),
                            showlegend=False,
                        )
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                except Exception:
                    pass

    # ── 5. POLICY COMPLIANCE ──────────────────────────────────────
    st.markdown('<div class="section-header">Policy Compliance</div>', unsafe_allow_html=True)
    _pol_mode_cls = "ok" if _pol_mode == "LIVE" else ("warn" if _pol_mode == "DRY_RUN" else "neutral")
    # Budget usage bar via HTML
    _budget_bar_color = "var(--success)" if _daily_pct < 60 else ("var(--warn)" if _daily_pct < 90 else "var(--danger)")
    st.markdown(f"""<div class="glass-card">
        <div class="kv-grid">
            <span class="kv-key">Mode</span><span class="kv-val {_pol_mode_cls}">{_html.escape(_pol_mode)}</span>
            <span class="kv-key">Max per tx</span><span class="kv-val">${_pf_policy.get('max_tx_usd', 0):.2f}</span>
            <span class="kv-key">Tx today</span><span class="kv-val">{_tx_count} / {_tx_max}</span>
            <span class="kv-key">Cooldown</span><span class="kv-val">{_pf_policy.get('cooldown_seconds', 0)}s</span>
        </div>
        <div style="margin-top:10px;">
            <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--muted);margin-bottom:4px;">
                <span>Daily Budget</span>
                <span>${_daily_spent:.2f} / ${_daily_max:.2f}</span>
            </div>
            <div style="height:8px;border-radius:4px;background:rgba(57,255,20,0.08);border:1px solid rgba(57,255,20,0.12);overflow:hidden;">
                <div style="height:100%;width:{min(_daily_pct, 100):.0f}%;background:{_budget_bar_color};border-radius:3px;transition:width 0.3s ease;"></div>
            </div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 6. TERMINAL LOG VIEWER ────────────────────────────────────
    st.markdown('<div class="section-header">Event Log</div>', unsafe_allow_html=True)
    _log_filter = st.selectbox("Filter", ["ALL", "trade", "swap", "bet", "alert", "deposit", "research", "decision"], key="log_filter_sel")
    try:
        _log_events = fin.get_financial_events(limit=100)
        # Also include decisions
        _log_decisions = fin.read_recent_decisions(limit=30)
        for _ld in _log_decisions:
            _ld["event"] = "decision"
            if "reasoning" in _ld:
                _ld["_msg"] = _ld["reasoning"]
        _all_log = _log_events + _log_decisions
        _all_log.sort(key=lambda x: x.get("ts", ""))
        if _log_filter != "ALL":
            _all_log = [e for e in _all_log if e.get("event") == _log_filter]
    except Exception:
        _all_log = []

    _log_display = _all_log[-50:]  # last 50 entries
    if _log_display:
        _log_lines = []
        for _li, _le in enumerate(_log_display, 1):
            _le_ts = _html.escape(str(_le.get("ts", ""))[:19])
            _le_evt = str(_le.get("event", "info"))
            _le_cls = _le_evt if _le_evt in ("trade", "swap", "bet", "alert", "error", "decision", "research") else "info"
            # Build message from available fields
            _le_parts = []
            for _fk in ("note", "_msg", "chain", "symbol", "value_usd", "reasoning"):
                _fv = _le.get(_fk)
                if _fv is not None and _fk not in ("event", "ts"):
                    _le_parts.append(f"{_fk}={_fv}" if _fk != "_msg" else str(_fv)[:120])
            _le_msg = _html.escape(" ".join(_le_parts)[:200]) if _le_parts else _html.escape(str({k: v for k, v in _le.items() if k not in ("ts", "event")})[:200])
            _log_lines.append(
                f'<div class="term-line">'
                f'<span class="term-ln">{_li}</span>'
                f'<span class="term-ts">{_le_ts}</span>'
                f'<span class="term-lvl {_le_cls}">{_html.escape(_le_evt)}</span>'
                f'<span class="term-msg">{_le_msg}</span>'
                f'</div>'
            )
        st.markdown(f'<div class="term-log">{"".join(_log_lines)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state"><div class="empty-icon">\u2588\u2588\u2588</div><div class="empty-text">No events logged yet. Log a test event below to verify.</div></div>', unsafe_allow_html=True)

    # ── 7. PERFORMANCE ────────────────────────────────────────────
    st.markdown('<div class="section-header">Performance</div>', unsafe_allow_html=True)
    try:
        _pf_history = fin.get_portfolio_history(limit=168)
        if len(_pf_history) >= 2:
            import plotly.graph_objects as go
            _hist_ts = [h.get("ts", "")[:16] for h in _pf_history]
            _hist_vals = [h.get("total_value_usd", 0) for h in _pf_history]
            _perf_color = "#39ff14" if _hist_vals[-1] >= _hist_vals[0] else "#ff5c5c"
            fig = go.Figure(go.Scatter(
                x=_hist_ts, y=_hist_vals, mode='lines',
                line=dict(color=_perf_color, width=2),
                fill='tozeroy',
                fillcolor=_perf_color.replace(")", ",0.06)").replace("rgb", "rgba") if "rgb" in _perf_color else f"rgba({','.join(str(int(_perf_color.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))},0.06)",
            ))
            fig.update_layout(
                height=220,
                margin=dict(l=0, r=0, t=10, b=20),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, color='#9ddc9d', tickfont=dict(size=9)),
                yaxis=dict(showgrid=True, gridcolor='rgba(57,255,20,0.06)', color='#9ddc9d', tickfont=dict(size=10), tickprefix='$'),
                showlegend=False, hovermode='x unified',
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown('<div class="empty-state"><div class="empty-icon">\U0001f4c8</div><div class="empty-text">Need 2+ snapshots for chart (hourly snapshots active)</div></div>', unsafe_allow_html=True)
    except Exception:
        st.markdown('<div class="empty-state"><div class="empty-icon">\U0001f4c8</div><div class="empty-text">Performance data unavailable</div></div>', unsafe_allow_html=True)
    # Daily P&L bar chart
    try:
        _trade_events = [e for e in _all_events if e.get("event") in ("trade", "swap", "bet")]
        if _trade_events:
            import plotly.graph_objects as go
            _daily_pnl: dict[str, float] = {}
            for e in _trade_events:
                day = str(e.get("ts", ""))[:10]
                pnl = float(e.get("pnl_usd", 0))
                _daily_pnl[day] = _daily_pnl.get(day, 0) + pnl
            if _daily_pnl:
                _days = list(_daily_pnl.keys())
                _pnls = list(_daily_pnl.values())
                _bar_colors = ["#39ff14" if v >= 0 else "#ff5c5c" for v in _pnls]
                fig = go.Figure(go.Bar(x=_days, y=_pnls, marker_color=_bar_colors))
                fig.update_layout(
                    height=180, margin=dict(l=0, r=0, t=10, b=20),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(showgrid=False, color='#9ddc9d', tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True, gridcolor='rgba(57,255,20,0.06)', color='#9ddc9d', tickfont=dict(size=10), tickprefix='$'),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception:
        pass

    # ── 8. POLYMARKET LIVE FEED ────────────────────────────────────
    st.markdown('<div class="section-header">Polymarket Live</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=30)
    def _fetch_polymarket_live():
        """Fetch live orders, trades, and market metadata from Polymarket CLOB."""
        import httpx
        result = {"orders": [], "trades": [], "error": None}
        try:
            _key_path = Path("/home/hackerman/agent-runtime/tools/agent-wallet-lab/keys/evm-key.json")
            if not _key_path.exists():
                result["error"] = "EVM key not found"
                return result
            _kd = json.loads(_key_path.read_text())
            _pk = _kd.get("private_key", "")
            from py_clob_client.client import ClobClient
            _clob = ClobClient("https://clob.polymarket.com", key=_pk, chain_id=137)
            _clob.set_api_creds(_clob.create_or_derive_api_creds())
            result["orders"] = _clob.get_orders() or []
            result["trades"] = _clob.get_trades() or []
        except Exception as _e:
            result["error"] = str(_e)[:200]
        # Resolve market questions from Gamma API using asset_id (clob token ID)
        _asset_ids = set()
        for _o in result["orders"]:
            _asset_ids.add(_o.get("asset_id", ""))
        for _t in result["trades"]:
            _asset_ids.add(_t.get("asset_id", ""))
        _asset_ids.discard("")
        result["market_meta"] = {}  # keyed by asset_id
        for _aid in list(_asset_ids)[:20]:
            try:
                _r = httpx.get(f"https://gamma-api.polymarket.com/markets?clob_token_ids={_aid}", timeout=5)
                _mdata = _r.json()
                if _mdata and isinstance(_mdata, list) and _mdata:
                    result["market_meta"][_aid] = _mdata[0]
            except Exception:
                pass
        return result

    _pm_live = _fetch_polymarket_live()

    if _pm_live.get("error"):
        st.markdown(f'<div class="glass-card"><div class="glass-meta" style="color:var(--warn);">CLOB API: {_html.escape(_pm_live["error"])}</div></div>', unsafe_allow_html=True)

    # ── 8a. Summary metrics ──────────────────────────────────────
    _pm_orders = _pm_live.get("orders", [])
    _pm_trades = _pm_live.get("trades", [])
    _pm_meta = _pm_live.get("market_meta", {})

    _total_invested = sum(float(t.get("size", 0)) * float(t.get("price", 0)) for t in _pm_trades)
    _total_shares = sum(float(t.get("size", 0)) for t in _pm_trades)
    _open_order_value = sum(float(o.get("original_size", 0)) * float(o.get("price", 0)) for o in _pm_orders)

    _pm_s1, _pm_s2, _pm_s3, _pm_s4 = st.columns(4)
    with _pm_s1:
        st.metric("Filled Trades", len(_pm_trades))
    with _pm_s2:
        st.metric("Open Orders", len(_pm_orders))
    with _pm_s3:
        st.metric("Invested", f"${_total_invested:.2f}")
    with _pm_s4:
        st.metric("Shares Held", f"{_total_shares:.0f}")

    # ── 8b. Filled positions ─────────────────────────────────────
    if _pm_trades:
        st.markdown('<div class="section-header" style="font-size:0.95rem;margin-top:16px;">Filled Positions</div>', unsafe_allow_html=True)
        for _t in _pm_trades:
            _t_size = float(_t.get("size", 0))
            _t_price = float(_t.get("price", 0))
            _t_cost = _t_size * _t_price
            _t_side = _t.get("side", "?")
            _t_outcome = _t.get("outcome", "?")
            _t_status = _t.get("status", "?")
            _t_asset_id = _t.get("asset_id", "")
            _t_tx = _t.get("transaction_hash", "")
            # Look up question from market meta by asset_id
            _t_meta = _pm_meta.get(_t_asset_id, {})
            _t_question = _t_meta.get("question", f"Market {_t_asset_id[:16]}...")
            # Current market price from meta
            _t_cur_price = None
            if _t_meta:
                try:
                    _prices = json.loads(_t_meta.get("outcomePrices", "[]"))
                    _t_cur_price = float(_prices[0]) if _prices else None
                except Exception:
                    pass
            # P&L calculation
            _t_pnl_html = ""
            if _t_cur_price is not None:
                _t_cur_val = _t_size * _t_cur_price
                _t_pnl = _t_cur_val - _t_cost
                _t_pnl_pct = (_t_pnl / _t_cost * 100) if _t_cost > 0 else 0
                _t_pnl_cls = "up" if _t_pnl >= 0 else "down"
                _t_pnl_html = f'<span class="pm-label">Unrealized P&L</span><span class="pm-val {_t_pnl_cls}">${_t_pnl:+.2f} ({_t_pnl_pct:+.0f}%)</span>'
                _t_pnl_html += f'<span class="pm-label">Mkt Price</span><span class="pm-val">{_t_cur_price:.1%}</span>'
            _t_max_payout = _t_size * 1.0  # $1 per share if resolves Yes
            _t_potential = _t_max_payout - _t_cost
            _t_potential_cls = "up" if _t_potential > 0 else ""
            _t_tx_short = f'{_t_tx[:10]}...' if _t_tx else "\u2014"
            st.markdown(f"""<div class="pos-card" style="margin-bottom:10px;">
                <div class="pos-header">
                    <span class="pos-sym" style="font-size:0.88rem;">{_html.escape(_t_question[:65])}</span>
                    <span class="pos-chain">{_html.escape(_t_status)}</span>
                </div>
                <div class="pos-metrics">
                    <span class="pm-label">{_t_side} {_t_outcome}</span><span class="pm-val">{_t_size:.0f} shares @ ${_t_price:.3f}</span>
                    <span class="pm-label">Cost</span><span class="pm-val">${_t_cost:.2f}</span>
                    <span class="pm-label">Max Payout</span><span class="pm-val {_t_potential_cls}">${_t_max_payout:.2f}</span>
                    {_t_pnl_html}
                    <span class="pm-label">Tx</span><span class="pm-val" style="font-size:0.65rem;">{_html.escape(_t_tx_short)}</span>
                </div>
                <div class="pos-pnl">
                    <div class="pnl-val up">${_t_potential:.2f}</div>
                    <div class="pnl-label">Potential Profit</div>
                </div>
            </div>""", unsafe_allow_html=True)

    # ── 8c. Open orders ──────────────────────────────────────────
    if _pm_orders:
        st.markdown('<div class="section-header" style="font-size:0.95rem;margin-top:16px;">Open Orders</div>', unsafe_allow_html=True)
        for _o in _pm_orders:
            _o_size = float(_o.get("original_size", 0))
            _o_matched = float(_o.get("size_matched", 0))
            _o_price = float(_o.get("price", 0))
            _o_cost = _o_size * _o_price
            _o_side = _o.get("side", "?")
            _o_outcome = _o.get("outcome", "?")
            _o_status = _o.get("status", "?")
            _o_type = _o.get("order_type", "?")
            _o_asset_id = _o.get("asset_id", "")
            _o_id = _o.get("id", "")[:16]
            # Question from meta by asset_id
            _o_meta = _pm_meta.get(_o_asset_id, {})
            _o_question = _o_meta.get("question", f"Market {_o_asset_id[:16]}...")
            _o_fill_pct = (_o_matched / _o_size * 100) if _o_size > 0 else 0
            _o_status_cls = "up" if _o_status == "LIVE" else "warn"
            st.markdown(f"""<div class="pos-card" style="margin-bottom:10px;border-color:rgba(255,179,71,0.25);">
                <div class="pos-header">
                    <span class="pos-sym" style="font-size:0.88rem;">{_html.escape(_o_question[:65])}</span>
                    <span class="pos-chain" style="color:var(--warn);">{_html.escape(_o_status)} \u00b7 {_html.escape(_o_type)}</span>
                </div>
                <div class="pos-metrics">
                    <span class="pm-label">{_o_side} {_o_outcome}</span><span class="pm-val">{_o_size:.0f} shares @ ${_o_price:.2f}</span>
                    <span class="pm-label">Max Cost</span><span class="pm-val">${_o_cost:.2f}</span>
                    <span class="pm-label">Filled</span><span class="pm-val">{_o_fill_pct:.0f}% ({_o_matched:.0f}/{_o_size:.0f})</span>
                    <span class="pm-label">Order ID</span><span class="pm-val" style="font-size:0.65rem;">{_html.escape(_o_id)}...</span>
                </div>
            </div>""", unsafe_allow_html=True)

    if not _pm_trades and not _pm_orders and not _pm_live.get("error"):
        st.markdown('<div class="empty-state"><div class="empty-icon">\U0001f3b2</div><div class="empty-text">No Polymarket positions or orders yet.</div></div>', unsafe_allow_html=True)

    # ── 8d. Trending Markets ─────────────────────────────────────
    with st.expander("Trending Markets (Polymarket)", expanded=False):
        try:
            @st.cache_data(ttl=300)
            def _fetch_polymarket():
                return fin.polymarket_get_markets(limit=8)
            _pm_markets = _fetch_polymarket()
            if _pm_markets:
                st.markdown('<div class="glass-grid">', unsafe_allow_html=True)
                for _pm in _pm_markets:
                    _pm_q = _html.escape(str(_pm.get("question", "?"))[:80])
                    _pm_vol = _pm.get("volume_24h", 0)
                    _pm_prices = _pm.get("outcome_prices", [])
                    _pm_outcomes = _pm.get("outcomes", [])
                    _pm_odds = ""
                    if _pm_prices and _pm_outcomes:
                        try:
                            prices = json.loads(_pm_prices) if isinstance(_pm_prices, str) else _pm_prices
                            outcomes = json.loads(_pm_outcomes) if isinstance(_pm_outcomes, str) else _pm_outcomes
                            parts = [f"{o}: {float(p)*100:.0f}%" for o, p in zip(outcomes[:2], prices[:2])]
                            _pm_odds = " \u00b7 ".join(parts)
                        except Exception:
                            _pm_odds = ""
                    _pm_vol_str = f"${float(_pm_vol):,.0f}" if _pm_vol else "\u2014"
                    st.markdown(f"""<div class="glass-card">
                        <div class="glass-title" style="font-size:0.85rem;">{_pm_q}</div>
                        <div class="glass-meta">{_pm_odds}</div>
                        <div class="glass-meta">24h vol: {_pm_vol_str}</div>
                    </div>""", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.caption("Could not fetch Polymarket data.")
        except Exception:
            st.caption("Polymarket data unavailable.")

    # ── 9. MEMORY BANK ────────────────────────────────────────────
    st.markdown('<div class="section-header">Memory Bank</div>', unsafe_allow_html=True)
    with st.expander("Current Strategy", expanded=False):
        _strategy = fin.read_strategy()
        if _strategy.strip():
            st.markdown(_strategy)
        else:
            st.caption("No strategy defined yet.")
    with st.expander("Recent Decisions", expanded=False):
        _decisions = fin.read_recent_decisions(limit=10)
        if _decisions:
            for _d in reversed(_decisions):
                _d_ts = _html.escape(str(_d.get("ts", "?"))[:16])
                _d_type = _html.escape(str(_d.get("type", "?")))
                _d_reason = _html.escape(str(_d.get("reasoning", ""))[:200])
                st.markdown(f"**[{_d_ts}] {_d_type}** \u2014 {_d_reason}")
        else:
            st.caption("No decisions recorded yet.")
    with st.expander("Rolling Context (for Ralph Loop)", expanded=False):
        _ctx = ""
        try:
            if fin.CONTEXT_FILE.exists():
                _ctx = fin.CONTEXT_FILE.read_text(encoding="utf-8")
        except Exception:
            pass
        if _ctx.strip():
            st.markdown(_ctx)
        else:
            st.caption("No rolling context generated yet.")
        if st.button("Regenerate Context", key="regen_ctx"):
            try:
                fin.update_rolling_context()
                _set_flash("success", "Rolling context regenerated.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

# ═══════════════════════════════════════════════════════════════════
# TAB 2: POLYMARKET
# ═══════════════════════════════════════════════════════════════════
with tabs[2]:
    try:
        from polymarket_tab import render_polymarket_tab
        render_polymarket_tab()
    except Exception as _pm_err:
        _page_context("Polymarket", "Active positions & weather scanner")
        st.error(f"Polymarket tab failed to load: {_pm_err}")
        st.caption("Check polymarket_tab.py exists and has no import errors.")

# ═══════════════════════════════════════════════════════════════════
# TAB 3: TELEGRAM
# ═══════════════════════════════════════════════════════════════════
with tabs[3]:
    _page_context("Telegram", "Operator communication channel")

    try:
        _tg_convo = fin.read_telegram_conversation(limit=50)
    except Exception:
        _tg_convo = []

    # Stats bar
    _tg_in_count = len([m for m in _tg_convo if m.get("direction") == "in"])
    _tg_out_count = len([m for m in _tg_convo if m.get("direction") == "out"])
    st.markdown(f"""
        <div class="data-strip">
            {_chip(f'Messages: {len(_tg_convo)}', 'neutral')}
            {_chip(f'Operator: {_tg_in_count}', 'ok')}
            {_chip(f'Agent: {_tg_out_count}', 'neutral')}
        </div>""", unsafe_allow_html=True)

    # Conversation
    if _tg_convo:
        st.markdown('<div class="glass-card" style="max-height:600px;overflow-y:auto;padding:1rem;">', unsafe_allow_html=True)
        for _tg in _tg_convo:
            _tg_ts = _html.escape(str(_tg.get("ts", ""))[:16])
            _tg_msg = _html.escape(str(_tg.get("message", "")))
            _tg_dir = _tg.get("direction", "in")
            if _tg_dir == "in":
                st.markdown(
                    f'<div style="margin:0.5rem 0;padding:0.5rem 0.8rem;border-left:3px solid var(--accent);border-radius:0 6px 6px 0;background:rgba(57,255,20,0.04);">'
                    f'<span style="font-size:0.65rem;opacity:0.5;font-family:monospace;">{_tg_ts} \u00b7 operator</span><br/>'
                    f'<span style="font-size:0.85rem;">{_tg_msg}</span></div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div style="margin:0.5rem 0;padding:0.5rem 0.8rem;border-right:3px solid #0af;border-radius:6px 0 0 6px;background:rgba(0,170,255,0.04);text-align:right;">'
                    f'<span style="font-size:0.65rem;opacity:0.5;font-family:monospace;">{_tg_ts} \u00b7 agent</span><br/>'
                    f'<span style="font-size:0.85rem;">{_tg_msg}</span></div>',
                    unsafe_allow_html=True
                )
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state"><div class="empty-icon">\U0001f4ac</div><div class="empty-text">No Telegram messages yet \u00b7 Send /msg in Telegram to start</div></div>', unsafe_allow_html=True)

    # Reply input
    _tg_reply_cols = st.columns([4, 1])
    with _tg_reply_cols[0]:
        _tg_reply_text = st.text_input("Reply via Telegram", key="tg_reply", placeholder="Type a message to send to Telegram...")
    with _tg_reply_cols[1]:
        st.markdown("<br/>", unsafe_allow_html=True)
        _tg_send = st.button("Send", key="tg_send_btn", use_container_width=True)
    if _tg_send and _tg_reply_text.strip():
        try:
            ok = fin.send_telegram(_tg_reply_text.strip())
            if ok:
                _set_flash("success", "Message sent to Telegram.")
            else:
                _set_flash("error", "Failed to send \u2014 check bot token config.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")

# ── Footer ───────────────────────────────────────────────────────
st.markdown(f'<div class="dashboard-footer">{datetime.now(PST).strftime("%Y-%m-%d %H:%M PST")}</div>', unsafe_allow_html=True)

if st.session_state.get("auto_refresh"):
    import time; time.sleep(0.1)
    st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)

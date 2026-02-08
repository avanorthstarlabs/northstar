from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import base64
import json
import hashlib
import streamlit as st
from lib.runtime import (
    read_mode, write_mode,
    read_inbox, write_inbox,
    trigger_run,
    latest_claude, latest_review,
    read_json_file,
    list_matching,
    stat_mtime_iso,
    extract_timestamp
)
import streamlit.components.v1 as components
import html as _html
from typing import Iterable
from lib.ollama import list_models, chat

APP_ROOT = Path(__file__).parent
LOGO_PATH = APP_ROOT / "assets" / "logo.svg"
ICON_PATH = APP_ROOT / "assets" / "icon.png"
PST = ZoneInfo("America/Los_Angeles")

page_icon = str(ICON_PATH) if ICON_PATH.exists() else ":)"
st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide", page_icon=page_icon, initial_sidebar_state="expanded")

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
        border-color: var(--accent) !important;
    }
    /* Glass grid & cards */
    .glass-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:12px 0 20px;}
    .glass-card {
        padding:16px 18px;border-radius:14px;
        background:var(--panel);
        border:1px solid var(--accent-border);
        backdrop-filter: blur(8px);
        box-shadow: 0 6px 24px rgba(0,0,0,0.35);
        transition: border-color 200ms ease, box-shadow 200ms ease;
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
    </style>
    """,
    unsafe_allow_html=True,
)

cols_title = st.columns([1, 8])
with cols_title[0]:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=72)
with cols_title[1]:
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
            <h1 style="margin:0; padding:0; font-size:1.8rem; letter-spacing:-0.02em;">
                Agent Runtime Dashboard
            </h1>
            <span class="pulse" style="margin-top:4px;"></span>
        </div>
        <div style="font-size:0.78rem; color:var(--muted); margin-top:-2px; letter-spacing:0.04em;">
            AUTONOMOUS ENGINEERING CONTROL CENTER
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

def _active_provider_model() -> tuple[str, str]:
    cfg = _routing_config()
    routing = _latest_routing()
    provider = (routing.get("provider") or cfg.get("force_provider") or cfg.get("default_provider") or "unknown").strip().lower()
    model = "—"
    if provider == "codex":
        model = str(cfg.get("codex_model", "gpt-5.2-codex"))
    elif provider == "claude":
        model = str(cfg.get("claude_model", "claude-opus-4-6"))
    elif provider == "ollama":
        model = str(cfg.get("ollama_model", "llama3.2:3b"))
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

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### ⚙️ Dashboard")

        # Quick status summary
        _sb_status, _sb_status_ts = _read_project_status()
        _sb_health, _sb_health_reason = _read_cycle_health()
        _sb_health_label, _sb_health_note = _cycle_label(_sb_health, _sb_status)
        _sb_health_icon = "🟢" if _sb_health_label == "ok" else ("🟡" if _sb_health_label == "warn" else ("🔴" if _sb_health_label == "error" else "⚪"))
        _sb_status_icon = {"IN_PROGRESS": "🔄", "DONE": "✅", "PENDING_HUMAN_REVIEW": "⏳"}.get(_sb_status, "❓")

        st.markdown(
            f"""
            <div style="border:1px solid rgba(57,255,20,0.2); border-radius:10px; padding:10px 12px; margin-bottom:12px;
                         background:rgba(7,12,7,0.5); font-size:0.85rem;">
                <div style="margin-bottom:4px;">{_sb_health_icon} <b>Cycle:</b> {_sb_health_label.upper()}</div>
                <div style="margin-bottom:4px;">{_sb_status_icon} <b>Project:</b> {_sb_status}</div>
                <div style="opacity:0.7;">Last status update: {_fmt_time(_sb_status_ts) if _sb_status_ts else '—'}</div>
                <div style="opacity:0.7;">Recent cycle health: {_sb_health_reason}{' · ' + _sb_health_note if _sb_health_note else ''}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        auto_refresh = st.toggle("Auto-refresh (30s)", value=False, key="auto_refresh")
        if auto_refresh:
            st.caption("Page will refresh every 30 seconds.")

        st.divider()
        st.markdown("### 🚀 Quick Actions")
        if st.button("🔄 Refresh now", key="sidebar_refresh", use_container_width=True):
            st.rerun()
        if st.button("📋 Brief me", key="sidebar_brief", use_container_width=True):
            st.session_state["_jump_to_brief"] = True
            st.rerun()
        if st.button("💬 Open chat", key="sidebar_chat", use_container_width=True):
            st.session_state["_jump_to_chat"] = True
            st.rerun()
        if st.button("📝 Notes", key="sidebar_notes", use_container_width=True):
            st.session_state["_jump_to_notes"] = True
            st.rerun()

        # Pinned note (quick sticky)
        st.divider()
        st.markdown("### 📌 Pinned Note")
        _pin_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/pinned_note.txt")
        _pin_text = ""
        if _pin_path.exists():
            try:
                _pin_text = _pin_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                pass
        if _pin_text:
            st.markdown(
                f'<div style="border:1px solid rgba(57,255,20,0.25); border-radius:8px; padding:8px 10px; '
                f'background:rgba(7,12,7,0.5); font-size:0.82rem; color:#eaffea; white-space:pre-wrap;">'
                f'{_html.escape(_pin_text[:200])}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No pinned note. Add one in the Notes tab.")


        st.divider()
        st.markdown("### 📊 Quick Stats")
        _sb_patterns = ["claude_*.json", "review_claude_*__by_openai.json"]
        _sb_all_files = list_matching(_sb_patterns)
        _sb_inbox_raw = read_inbox()
        _sb_inbox_lines = len([l for l in _sb_inbox_raw.splitlines() if l.strip()])
        st.caption(f"📄 {len(_sb_all_files)} proposals")
        st.caption(f"📥 {_sb_inbox_lines} inbox items")
        _sb_last_cycle = _last_cycle_ts()
        if _sb_last_cycle:
            _sb_age = (datetime.now(timezone.utc) - _sb_last_cycle).total_seconds() / 60.0
            if _sb_age < 60:
                st.caption(f"⏱️ Last cycle: {_sb_age:.0f}m ago")
            else:
                st.caption(f"⏱️ Last cycle: {_sb_age/60:.1f}h ago")
        else:
            st.caption("⏱️ No cycle history")

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
        _touch_trigger("continue_work")
        st.warning("Set to IN_PROGRESS")
        st.rerun()
    if c2.button("Cancel"):
        st.info("Cancelled")
        st.rerun()

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
    def _ts(obj: dict) -> str:
        return obj.get("ts", "")
    items.sort(key=_ts, reverse=True)
    latest = items[0]
    summary = _summarize_event(latest)
    status = "active"
    if latest.get("event") in ("proposal_skipped",) or "no activity" in summary.lower():
        status = "idle"
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

_render_sidebar()

with tabs[0]:
    st.markdown('<div class="section-header">Status Snapshot</div>', unsafe_allow_html=True)

    patterns = ["claude_*.json", "review_claude_*__by_openai.json"]
    all_files = list_matching(patterns)
    latest_any = _latest_file(all_files)
    latest_review_file = _latest_file([p for p in all_files if p.name.startswith("review_claude_")])
    inbox_raw = read_inbox()

    snapshot_col, activity_col = st.columns([1.3, 1], gap="large")
    with snapshot_col:
        st.markdown('<div class="section-header" style="margin-top:0;">📊 Snapshot</div>', unsafe_allow_html=True)

        # Top row: key numbers
        row1 = st.columns(4)
        row1[0].metric("Proposals", len(all_files))
        row1[1].metric("Inbox items", len([l for l in inbox_raw.splitlines() if l.strip()]))
        row1[2].metric("Latest activity", _fmt_time(stat_mtime_iso(latest_any)) if latest_any else "—")
        row1[3].metric("Latest review", _fmt_time(stat_mtime_iso(latest_review_file)) if latest_review_file else "—")

        # Second row: system health
        health, reason = _read_cycle_health()
        _ps, _ = _read_project_status()
        health_label, _ = _cycle_label(health, _ps)
        provider, model = _active_provider_model()
        credit_status, credit_note = _credit_snapshot()

        row2 = st.columns(3)
        row2[0].metric("Cycle health", health_label.upper())
        row2[1].metric("Provider", provider.upper() if provider else "UNKNOWN")
        row2[2].metric("Credits", credit_status.upper())

        # Contextual caption
        st.markdown(
            f'<div style="font-size:0.78rem; color:var(--muted); margin:-6px 0 8px; line-height:1.6;">'
            f'🔧 {reason} · Patch: <code>{_latest_patch_name()}</code><br>'
            f'🤖 Model: <code>{model}</code> · {credit_note}'
            f'</div>',
            unsafe_allow_html=True,
        )

        failures = _recent_failures(2)
        dismissed = _load_dismissed_errors()
        if failures:
            st.markdown("**Recent failures**")
            show_dismissed = st.toggle("Show dismissed", value=False, key="show_dismissed_errors")
            for line in failures:
                err_id = _error_id(line)
                if (err_id in dismissed) and not show_dismissed:
                    continue
                c_err, c_btn = st.columns([18, 2])
                with c_err:
                    _failure_row(line[:400], key=err_id)
                with c_btn:
                    label = "Dismiss" if err_id not in dismissed else "Undismiss"
                    if st.button(label, key=f"dismiss_{err_id}"):
                        if err_id in dismissed:
                            dismissed.remove(err_id)
                        else:
                            dismissed.add(err_id)
                        _save_dismissed_errors(dismissed)
                        st.rerun()
        else:
            st.caption("No recent failures.")

    with activity_col:
        st.markdown('<div class="section-header" style="margin-top:0;">🤖 Agent Activity</div>', unsafe_allow_html=True)
        status, detail = _agent_activity()
        status_label = "CONNECTED" if status == "active" else ("IDLE" if status == "idle" else "UNKNOWN")
        accent = "var(--accent)" if status == "active" else "var(--muted)"
        pulse = '<span class="pulse"></span>' if status == "active" else ""
        st.markdown(
            f"""
            <div class="glass-card">
                <div class="glass-title" style="font-size:1rem;">Agent Connection</div>
                <div class="glass-meta" style="margin:8px 0 4px;">Status: {pulse}<span style="color:{accent};font-weight:700;font-size:0.95rem;">{status_label}</span></div>
                <div class="glass-meta" style="line-height:1.6;">{detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        feed = _activity_feed(limit=6)
        if feed:
            st.markdown(
                '<div style="font-size:0.85rem; font-weight:600; color:var(--accent); margin:14px 0 6px;">Live Activity</div>',
                unsafe_allow_html=True,
            )
            for item in feed:
                st.markdown(
                    f'<div style="font-size:0.8rem; color:var(--text); padding:3px 0; border-left:2px solid var(--accent-border); padding-left:10px; margin:2px 0;">'
                    f'<span style="color:var(--muted);">{_fmt_time(item["ts"])}</span> · {item["summary"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No recent activity found.")

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
        last_cycle = _last_cycle_ts()
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
    st.caption("Summarize inbox and latest proposals with local Ollama.")

    try:
        models = list_models(timeout=4)
        st.caption("Ollama status: reachable")
        # warm-up ping (non-blocking on failure)
        try:
            from lib.ollama import generate
            _ = generate(models[0], "ping", timeout=3) if models else ""
        except Exception:
            pass
    except Exception as e:
        models = []
        st.error(f"Could not reach Ollama at 127.0.0.1:11434 — {e}")

    if not models:
        st.warning("No Ollama models found. Pull one: ollama pull qwen2.5-coder:3b (or similar)")
    else:
        default_model = "llama3.2:3b"
        default_index = models.index(default_model) if default_model in models else 0
        model = st.selectbox("Model", models, index=default_index, key="brief_model")
        if st.button("Brief me"):
            inbox_text = inbox_raw.strip()
            cpath = latest_claude()
            rpath = latest_review()

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
                    from lib.ollama import generate
                    out = generate(model, prompt, timeout=60)
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
    projects = [p for p in projects_root.iterdir() if p.is_dir()]

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
        st.info("No projects found.")
    else:
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
            thumb_html = f'<img src="{thumb}" style="width:100%;border-radius:10px;margin:8px 0 10px;" />' if thumb else ""
            preview_html = f'<a href="{preview}" target="_blank" style="color:var(--accent);text-decoration:none;">Open Preview →</a>' if preview else ""
            cards.append(
                f"""
                <div class="glass-card">
                    <div class="glass-title">{p.name}</div>
                    <div class="glass-meta">Status: {status}</div>
                    <div class="glass-meta">Updated: {_fmt_time(ts) if ts else last_mod}</div>
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
    st.subheader("Projects")
    projects_root = Path("/home/hackerman/agent-runtime/workspace/projects")
    projects = [p for p in projects_root.iterdir() if p.is_dir()]

    def _read_lines(path: Path, max_lines: int = 6) -> list[str]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return [ln for ln in lines if ln.strip()][:max_lines]
        except Exception:
            return []

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

    def _recent_updates() -> list[dict]:
        items = []
        for p in projects:
            changelog = p / "CHANGELOG.md"
            if changelog.exists():
                lines = _read_lines(changelog, 8)
                if lines:
                    items.append({
                        "project": p.name,
                        "mtime": changelog.stat().st_mtime,
                        "lines": lines,
                    })
        return sorted(items, key=lambda x: x["mtime"], reverse=True)

    if not projects:
        st.info("No projects found.")
    else:
        cols = st.columns([2, 3])
        with cols[0]:
            st.markdown("**Project status**")
            for p in sorted(projects):
                status, ts = _project_status(p)
                last_mod = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                st.markdown(f"**{p.name}**")
                st.caption(f"Status: {status} · Updated: {_fmt_time(ts) if ts else _fmt_mtime(p)}")
                done_path = p / "DONE.md"
                if done_path.exists():
                    st.caption("DONE.md present")
                st.divider()
        with cols[1]:
            st.markdown("**Recent updates (plaintext)**")
            updates = _recent_updates()
            if not updates:
                st.info("No CHANGELOG entries found.")
            for item in updates[:10]:
                st.markdown(f"**{item['project']}**")
                st.code("\n".join(item["lines"]), language="text")

with tabs[2]:
    st.subheader("Inbox (directives/priorities/00_inbox.md)")
    inbox = st.text_area("Edit", value=read_inbox(), height=420)
    if st.button("Save inbox"):
        write_inbox(inbox)
        st.success("Inbox saved")

with tabs[4]:
    st.subheader("Latest outputs")
    st.caption("Browse proposals and reviews with a master-detail view.")
    patterns = ["claude_*.json", "review_claude_*__by_openai.json"]
    all_files = list_matching(patterns)

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
        st.info("No matching proposal files found.")
    else:
        claude_files = [p for p in all_files if p.name.startswith("claude_")]
        review_files = [p for p in all_files if p.name.startswith("review_claude_")]
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
                kind = "Claude proposal" if p.name.startswith("claude_") else "OpenAI review"
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

with tabs[3]:
    st.subheader("Timeline")
    patterns = ["claude_*.json", "review_claude_*__by_openai.json"]
    files = list_matching(patterns)

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
        st.info("No proposal files found yet.")
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
    st.subheader("Control")
    current_mode = read_mode()
    mode = st.radio("Mode", ["DIRECTED", "AUTONOMOUS"], index=0 if current_mode=="DIRECTED" else 1)
    if mode != current_mode:
        write_mode(mode)
        st.success(f"Mode set to {mode}")

    if st.button("Trigger run"):
        trigger_run()
        st.success("Triggered (wrote .trigger)")

    st.divider()
    st.subheader("Diagnostics")
    provider, model = _active_provider_model()
    credit_status, credit_note = _credit_snapshot()
    st.markdown(f"**Credits & usage**: {credit_status.upper()} · Provider: {provider.upper() if provider else 'UNKNOWN'} · Model: {model}")
    st.caption(credit_note)
    if st.button("Test Brief me (fast)"):
        try:
            models = list_models(timeout=4)
            if not models:
                st.error("No Ollama models available.")
            else:
                from lib.ollama import generate
                out = generate(models[0], "Reply with: OK", timeout=10)
                st.success(f"Brief me test OK: {out.strip()[:50]}")
        except Exception as e:
            st.error(f"Brief me test failed: {e}")

    st.divider()
    st.subheader("Review controls")
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    current_status = "UNKNOWN"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            current_status = data.get("status", "UNKNOWN")
        except Exception:
            current_status = "UNKNOWN"
    st.caption(f"Current status: {current_status}")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Approve (DONE)"):
            _confirm_done()

    with cols[1]:
        if st.button("Continue work"):
            _confirm_continue()

with tabs[6]:
    st.subheader("Local Ollama chat")
    try:
        models = list_models()
    except Exception as e:
        models = []
        st.error(f"Could not reach Ollama at 127.0.0.1:11434 — {e}")

    if not models:
        st.warning("No Ollama models found. Pull one: ollama pull qwen2.5-coder:3b (or similar)")
    else:
        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        if st.session_state["chat_history"]:
            st.markdown(f"**Conversation history** ({len(st.session_state['chat_history']) // 2} exchanges)")
            for msg in st.session_state["chat_history"][-10:]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        model = st.selectbox("Model", models, index=0)

        # Use session state for prompt to survive quick-prompt reruns
        _default_prompt = st.session_state.pop("_qp_prompt", "")
        prompt = st.text_area("Prompt", value=_default_prompt, height=220, help="Ask anything (local-only).", key="chat_prompt_area")
        if _default_prompt:
            st.info("Quick prompt loaded — click 'Send to Ollama' to run it.")
        
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

        if st.button("Send to Ollama"):
            if not prompt.strip():
                st.warning("Type a prompt first.")
            else:
                with st.spinner("Thinking..."):
                    out = chat(model, prompt)
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
    st.subheader("System Logs")
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
    st.subheader("System Health")
    st.caption("At-a-glance reliability metrics and recent cycle history.")

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

    # ── Ollama connectivity ──────────────────────────────────────
    st.divider()
    st.markdown("**Ollama connectivity**")
    try:
        _models = list_models(timeout=4)
        if _models:
            st.success(f"Ollama reachable — {len(_models)} model(s): {', '.join(_models[:5])}")
        else:
            st.warning("Ollama reachable but no models loaded.")
    except Exception as exc:
        st.error(f"Ollama unreachable: {exc}")

    if st.button("Refresh health", key="health_refresh"):
        st.rerun()


with tabs[9]:
    st.subheader("Daily Digest")
    st.caption("A comprehensive summary of recent agent activity, generated locally via Ollama.")

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

    try:
        digest_models = list_models(timeout=4)
    except Exception:
        digest_models = []

    if not digest_models:
        st.warning("No Ollama models available. Pull one to enable digest generation.")
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
                    from lib.ollama import generate
                    digest_out = generate(digest_model, digest_prompt, timeout=30)
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
    st.subheader("Notes & Scratchpad")
    st.caption("Persistent notes for yourself. Pinned note shows in the sidebar.")

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
    _pin_new = st.text_area("Pinned note", value=_pin_current, height=100, key="pinned_note_edit",
                            placeholder="e.g. 'Focus on health tab styling today'")
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

    _new_note = st.text_area("New note", height=120, key="new_scratch_note",
                             placeholder="Type a note and click Save…")
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

# Auto-refresh implementation
if st.session_state.get("auto_refresh"):
    import time
    time.sleep(0.1)  # small delay to let page render
    st.markdown(
        '<meta http-equiv="refresh" content="30">',
        unsafe_allow_html=True,
    )

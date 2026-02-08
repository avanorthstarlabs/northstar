from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import base64
import json
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
st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide", page_icon=page_icon)

cols_title = st.columns([1, 8])
with cols_title[0]:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=72)
with cols_title[1]:
    st.title("Agent Runtime Dashboard")

tabs = st.tabs(["Overview", "Projects", "Inbox", "Outputs", "Timeline", "Settings", "Chat", "Logs"])

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

def _copy_button(text: str, key: str) -> None:
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    html = f"""
    <style>
    html, body {{ margin:0; padding:0; background:transparent; }}
    .copy-btn {{
        background:transparent;
        border:1px solid #39ff14;
        color:#39ff14;
        padding:6px 10px;
        border-radius:8px;
        cursor:pointer;
        box-shadow:0 0 12px rgba(57,255,20,0.6);
        transition: all 120ms ease;
    }}
    .copy-btn:active {{
        transform: scale(0.96);
        box-shadow:0 0 20px rgba(57,255,20,0.9);
    }}
    </style>
    <button class="copy-btn" title="Copy to clipboard"
        onclick="navigator.clipboard.writeText(`{safe}`); this.innerText='✓'; setTimeout(()=>this.innerText='⧉', 800);">⧉</button>
    """
    components.html(html, height=34, width=50)

def _failure_row(text: str) -> None:
    safe = _html.escape(text)
    html = f"""
    <style>
    html, body {{ margin:0; padding:0; background:transparent; }}
    .row {{ display:flex; gap:12px; align-items:flex-start; }}
    .card {{
        flex:1;
        border:1px solid rgba(57,255,20,0.25);
        background:rgba(0,0,0,0.35);
        border-radius:12px;
        padding:10px 12px;
        box-shadow:0 8px 24px rgba(0,0,0,0.35);
    }}
    .copy {{
        min-width:34px; height:34px; display:flex; align-items:center; justify-content:center;
        border:1px solid #39ff14; color:#39ff14; border-radius:8px; cursor:pointer;
        box-shadow:0 0 12px rgba(57,255,20,0.6); background:transparent;
    }}
    pre {{
        margin:0;
        background:transparent;
        color:#eaffea; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        white-space:pre-wrap; word-break:break-word; max-height:72px; overflow:hidden;
    }}
    </style>
    <div class="row">
        <button class="copy" onclick="navigator.clipboard.writeText(`{safe}`)">⧉</button>
        <div class="card"><pre>{safe}</pre></div>
    </div>
    """
    components.html(html, height=90, width=1200)

def _agent_activity() -> tuple[str, str]:
    log_path = Path("/home/hackerman/agent-runtime/logs/router_events.jsonl")
    if not log_path.exists():
        return "unknown", "router log missing"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-200:]):
            if "\"event\": \"proposal_ok\"" in line or "\"event\": \"executor_run\"" in line:
                return "active", "agents recently processed a cycle"
            if "\"event\": \"proposal_skipped\"" in line:
                return "idle", "no new projects; proposals skipped"
        return "idle", "no recent agent activity found"
    except Exception:
        return "unknown", "failed to parse router log"

with tabs[0]:
    st.markdown(
        """
        <style>
        :root {
            --bg: #050705;
            --panel: rgba(7, 12, 7, 0.72);
            --accent: #39ff14;
            --accent-soft: rgba(57, 255, 20, 0.18);
            --text: #eaffea;
            --muted: #9ddc9d;
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
        }
        .stButton>button:hover {
            background: var(--accent-soft);
            border-color: var(--accent);
        }
        div[data-baseweb="select"] > div {
            border-color: var(--accent) !important;
        }
        .glass-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:8px 0 18px;}
        .glass-card {
            padding:14px 16px;border-radius:14px;
            background:var(--panel);
            border:1px solid var(--accent-soft);
            backdrop-filter: blur(8px);
            box-shadow: 0 6px 24px rgba(0,0,0,0.35);
        }
        .glass-title {font-weight:600;font-size:0.95rem;margin-bottom:6px;color:var(--accent);}
        .glass-meta {opacity:0.8;font-size:0.8rem;color:var(--muted);}
        .pulse {
            display:inline-block;
            width:10px;height:10px;border-radius:999px;
            margin-right:8px;background:var(--accent);
            box-shadow:0 0 12px rgba(57,255,20,0.6);
            animation:pulse 1.6s ease-in-out infinite;
        }
        @keyframes pulse {
            0% {transform:scale(0.9); opacity:0.6;}
            50% {transform:scale(1.2); opacity:1;}
            100% {transform:scale(0.9); opacity:0.6;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Status snapshot")
    patterns = ["claude_*.json", "review_claude_*__by_openai.json"]
    all_files = list_matching(patterns)
    latest_any = _latest_file(all_files)
    latest_review_file = _latest_file([p for p in all_files if p.name.startswith("review_claude_")])
    inbox_raw = read_inbox()

    cols = st.columns(5)
    cols[0].metric("Total proposals", len(all_files))
    cols[1].metric("Latest activity", _fmt_time(stat_mtime_iso(latest_any)) if latest_any else "—")
    cols[2].metric("Latest review", _fmt_time(stat_mtime_iso(latest_review_file)) if latest_review_file else "—")
    cols[3].metric("Inbox lines", len([l for l in inbox_raw.splitlines() if l.strip()]))
    health, reason = _read_cycle_health()
    cols[4].metric("Cycle health", health.upper())
    st.caption(f"Health: {reason} · Last patch: {_latest_patch_name()}")
    failures = _recent_failures(2)
    if failures:
        st.markdown("**Recent failures**")
        for line in failures:
            _failure_row(line[:400])

    st.divider()
    status, detail = _agent_activity()
    status_label = "CONNECTED" if status == "active" else ("IDLE" if status == "idle" else "UNKNOWN")
    accent = "var(--accent)" if status == "active" else "var(--muted)"
    pulse = '<span class="pulse"></span>' if status == "active" else ""
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="glass-title">Agent connection</div>
            <div class="glass-meta">Status: {pulse}<span style="color:{accent};font-weight:600;">{status_label}</span></div>
            <div class="glass-meta">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("**Action required**")
    status_path = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard/status.json")
    current_status = "UNKNOWN"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            current_status = data.get("status", "UNKNOWN")
        except Exception:
            current_status = "UNKNOWN"
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

    st.subheader("Brief me")
    st.write("Summarize inbox and latest proposals with local Ollama.")

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
        model = st.selectbox("Model", models, index=0, key="brief_model")
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
                "INBOX:\n"
                f"{inbox_text or '(empty)'}\n\n"
                "LATEST_CLAUDE_PROPOSAL_JSON:\n"
                f"{_json_blob(cpath)}\n\n"
                "LATEST_OPENAI_REVIEW_JSON:\n"
                f"{_json_blob(rpath)}\n"
            )
            with st.spinner("Briefing..."):
                try:
                    from lib.ollama import generate
                    out = generate(model, prompt, timeout=20)
                    st.session_state["briefing"] = out
                except Exception as e:
                    st.error(f"Briefing failed or timed out: {e}")

        if "briefing" in st.session_state:
            st.text_area("Briefing", value=st.session_state["briefing"], height=320)

    st.subheader("Project overview")
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
        st.markdown("**Activity feed (latest project updates)**")
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

    query = st.text_input("Search", placeholder="Filter by filename...")
    max_items = st.slider("Max items", min_value=5, max_value=100, value=20, step=5)

    filtered = [p for p in all_files if query.lower() in p.name.lower()] if query else all_files

    if not filtered:
        st.info("No matching proposal files found.")
    else:
        if "selected_output" not in st.session_state:
            st.session_state["selected_output"] = str(filtered[0])

        grouped: dict[str, list[Path]] = {}
        for p in filtered:
            meta = _summarize_output(p)
            key = _project_key(meta, p.name)
            grouped.setdefault(key, []).append(p)

        st.markdown("**Projects**")
        proj_cols = st.columns(min(4, max(1, len(grouped))))
        for idx, (project, items) in enumerate(sorted(grouped.items())):
            with proj_cols[idx % len(proj_cols)]:
                st.caption(project)
                latest = max(items, key=lambda x: extract_timestamp(x))
                meta = _summarize_output(latest)
                if st.button(f"Open latest", key=f"open_latest_{project}"):
                    st.session_state["selected_output"] = str(latest)

        st.divider()
        st.markdown("**All proposals (clean labels)**")
        for p in filtered[:max_items]:
            with st.container():
                cols = st.columns([6, 2, 1])
                with cols[0]:
                    meta = _summarize_output(p)
                    st.markdown(f"**{_clean_label(p, meta)}**")
                    st.caption(f"{_fmt_time(stat_mtime_iso(p))} · {p.stat().st_size} bytes")
                    if meta["summary"]:
                        st.markdown(f"- {meta['summary']}")
                with cols[1]:
                    kind = "Claude proposal" if p.name.startswith("claude_") else "OpenAI review"
                    st.write(kind)
                    if meta["mode"]:
                        st.caption(f"Mode: {meta['mode']}")
                    if meta["proposal_id"]:
                        st.caption(f"ID: {meta['proposal_id']}")
                with cols[2]:
                    if st.button("Open", key=f"view_{p.name}"):
                        st.session_state["selected_output"] = str(p)
                st.divider()

        sel = st.session_state.get("selected_output")
        if sel:
            p = Path(sel)
            st.subheader(f"Viewer: {p.name}")
            try:
                st.json(read_json_file(p))
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
        model = st.selectbox("Model", models, index=0)
        prompt = st.text_area("Prompt", height=220, placeholder="Ask anything (local-only).")
        if st.button("Send to Ollama"):
            if not prompt.strip():
                st.warning("Type a prompt first.")
            else:
                with st.spinner("Thinking..."):
                    out = chat(model, prompt)
                st.text_area("Response", value=out, height=260)

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

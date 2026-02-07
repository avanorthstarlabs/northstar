from __future__ import annotations
from pathlib import Path
from datetime import datetime
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
from lib.ollama import list_models, chat

APP_ROOT = Path(__file__).parent
LOGO_PATH = APP_ROOT / "assets" / "logo.svg"
ICON_PATH = APP_ROOT / "assets" / "icon.png"

page_icon = str(ICON_PATH) if ICON_PATH.exists() else ":)"
st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide", page_icon=page_icon)

cols_title = st.columns([1, 8])
with cols_title[0]:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=72)
with cols_title[1]:
    st.title("Agent Runtime Dashboard")

tabs = st.tabs(["Overview", "Inbox", "Outputs", "Timeline", "Settings", "Chat"])

with tabs[0]:
    st.subheader("Brief me")
    st.write("Summarize inbox and latest proposals with local Ollama.")

    try:
        models = list_models()
    except Exception as e:
        models = []
        st.error(f"Could not reach Ollama at 127.0.0.1:11434 — {e}")

    if not models:
        st.warning("No Ollama models found. Pull one: ollama pull qwen2.5-coder:3b (or similar)")
    else:
        model = st.selectbox("Model", models, index=0, key="brief_model")
        if st.button("Brief me"):
            inbox_text = read_inbox().strip()
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
                "You are a private agent assistant. Summarize the inbox and the latest proposals.\n"
                "Return a short briefing with: (1) top priorities, (2) risks/blocks, (3) next actions.\n\n"
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
                    out = generate(model, prompt)
                    st.session_state["briefing"] = out
                except Exception as e:
                    st.error(f"Briefing failed: {e}")

        if "briefing" in st.session_state:
            st.text_area("Briefing", value=st.session_state["briefing"], height=320)

with tabs[1]:
    st.subheader("Inbox (directives/priorities/00_inbox.md)")
    inbox = st.text_area("Edit", value=read_inbox(), height=420)
    if st.button("Save inbox"):
        write_inbox(inbox)
        st.success("Inbox saved")

with tabs[2]:
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

    query = st.text_input("Search", placeholder="Filter by filename...")
    max_items = st.slider("Max items", min_value=5, max_value=100, value=20, step=5)

    filtered = [p for p in all_files if query.lower() in p.name.lower()] if query else all_files

    if not filtered:
        st.info("No matching proposal files found.")
    else:
        if "selected_output" not in st.session_state:
            st.session_state["selected_output"] = str(filtered[0])

        for p in filtered[:max_items]:
            with st.container():
                cols = st.columns([6, 2, 1])
                with cols[0]:
                    meta = _summarize_output(p)
                    st.markdown(f"**{p.name}**")
                    st.caption(f"{stat_mtime_iso(p)} · {p.stat().st_size} bytes")
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
                    if st.button("View", key=f"view_{p.name}"):
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

with tabs[4]:
    st.subheader("Control")
    current_mode = read_mode()
    mode = st.radio("Mode", ["DIRECTED", "AUTONOMOUS"], index=0 if current_mode=="DIRECTED" else 1)
    if mode != current_mode:
        write_mode(mode)
        st.success(f"Mode set to {mode}")

    if st.button("Trigger run"):
        trigger_run()
        st.success("Triggered (wrote .trigger)")

with tabs[5]:
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

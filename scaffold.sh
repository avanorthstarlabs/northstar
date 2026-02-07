#!/usr/bin/env bash
set -euo pipefail

# This dashboard lives HERE (current folder), and reads/writes your runtime in ~/agent-runtime
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="/home/hackerman/agent-runtime"

mkdir -p "$HERE/lib"

cat > "$HERE/lib/runtime.py" <<'PY'
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

RUNTIME = Path("/home/hackerman/agent-runtime")
MODE_FILE = RUNTIME / "constitution" / "mode.state"
INBOX_FILE = RUNTIME / "directives" / "priorities" / "00_inbox.md"
TRIGGER_FILE = RUNTIME / "directives" / "priorities" / ".trigger"
PROPOSALS_DIR = RUNTIME / "planner" / "proposals"

def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def read_mode() -> str:
    if MODE_FILE.exists():
        s = MODE_FILE.read_text(encoding="utf-8").strip()
        s = s.replace("MODE:", "").strip()
        if s in ("DIRECTED", "AUTONOMOUS"):
            return s
    return "DIRECTED"

def write_mode(mode: str) -> None:
    mode = mode.strip().upper()
    if mode not in ("DIRECTED", "AUTONOMOUS"):
        raise ValueError("mode must be DIRECTED or AUTONOMOUS")
    _ensure_parent(MODE_FILE)
    MODE_FILE.write_text(f"MODE: {mode}\n", encoding="utf-8")

def read_inbox() -> str:
    if INBOX_FILE.exists():
        return INBOX_FILE.read_text(encoding="utf-8")
    return ""

def write_inbox(text: str) -> None:
    _ensure_parent(INBOX_FILE)
    INBOX_FILE.write_text(text, encoding="utf-8")

def trigger_run() -> None:
    _ensure_parent(TRIGGER_FILE)
    ts = datetime.now(timezone.utc).isoformat()
    with TRIGGER_FILE.open("a", encoding="utf-8") as f:
        f.write(f"# trigger {ts}\n")

def _latest_matching(prefix: str) -> Path | None:
    if not PROPOSALS_DIR.exists():
        return None
    files = sorted(PROPOSALS_DIR.glob(prefix), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def latest_claude() -> Path | None:
    return _latest_matching("claude_*.json")

def latest_review() -> Path | None:
    return _latest_matching("review_claude_*__by_openai.json")

def read_json_file(p: Path) -> dict:
    data = p.read_text(encoding="utf-8")
    return json.loads(data)
PY

cat > "$HERE/lib/ollama.py" <<'PY'
from __future__ import annotations
import requests

OLLAMA = "http://127.0.0.1:11434"

def list_models() -> list[str]:
    # /api/tags returns {"models":[{"name":"..."}]}
    r = requests.get(f"{OLLAMA}/api/tags", timeout=10)
    r.raise_for_status()
    j = r.json()
    models = [m.get("name") for m in j.get("models", []) if m.get("name")]
    return models

def chat(model: str, prompt: str) -> str:
    # Use generate endpoint; stream=false for simplicity
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = requests.post(f"{OLLAMA}/api/generate", json=payload, timeout=120)
    r.raise_for_status()
    j = r.json()
    return j.get("response", "")
PY

cat > "$HERE/app.py" <<'PY'
import streamlit as st
from lib.runtime import (
    read_mode, write_mode,
    read_inbox, write_inbox,
    trigger_run,
    latest_claude, latest_review,
    read_json_file
)
from lib.ollama import list_models, chat

st.set_page_config(page_title="Agent Runtime Dashboard", layout="wide")

st.title("Agent Runtime Dashboard")

# Sidebar controls
with st.sidebar:
    st.header("Control")
    current_mode = read_mode()
    mode = st.radio("Mode", ["DIRECTED", "AUTONOMOUS"], index=0 if current_mode=="DIRECTED" else 1)
    if mode != current_mode:
        write_mode(mode)
        st.success(f"Mode set to {mode}")

    if st.button("Trigger run"):
        trigger_run()
        st.success("Triggered (wrote .trigger)")

# Main layout
colA, colB = st.columns([1, 1])

with colA:
    st.subheader("Inbox (directives/priorities/00_inbox.md)")
    inbox = st.text_area("Edit", value=read_inbox(), height=260)
    if st.button("Save inbox"):
        write_inbox(inbox)
        st.success("Inbox saved")

    st.subheader("Latest outputs")
    cpath = latest_claude()
    rpath = latest_review()

    if cpath:
        with st.expander(f"Claude proposal: {cpath.name}", expanded=True):
            try:
                st.json(read_json_file(cpath))
            except Exception as e:
                st.error(f"Failed to read JSON: {e}")
                st.code(cpath.read_text(encoding='utf-8')[:12000])
    else:
        st.info("No claude_*.json found yet.")

    if rpath:
        with st.expander(f"OpenAI review: {rpath.name}", expanded=False):
            try:
                st.json(read_json_file(rpath))
            except Exception as e:
                st.error(f"Failed to read JSON: {e}")
                st.code(rpath.read_text(encoding='utf-8')[:12000])
    else:
        st.info("No review_claude_*__by_openai.json found yet.")

with colB:
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
PY

cat > "$HERE/README.md" <<'MD'
# Agent Runtime Dashboard (local)

## Install deps (inside your venv)
source /home/hackerman/agent-runtime/.venv/bin/activate
python -m pip install streamlit requests

## Run
cd /home/hackerman/agent-runtime/workspace/projects/agent-dashboard
streamlit run app.py --server.port 8787

Open: http://localhost:8787
MD

echo "[ok] scaffold created in: $HERE"

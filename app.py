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

tabs = st.tabs(["Overview", "Inbox", "Outputs", "Timeline", "Settings", "Chat"])

with tabs[0]:
    st.subheader("Brief me")
    st.write("Summarize inbox and latest proposals with local Ollama.")
    st.info("Briefing will be wired in a later patch.")

with tabs[1]:
    st.subheader("Inbox (directives/priorities/00_inbox.md)")
    inbox = st.text_area("Edit", value=read_inbox(), height=420)
    if st.button("Save inbox"):
        write_inbox(inbox)
        st.success("Inbox saved")

with tabs[2]:
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

with tabs[3]:
    st.subheader("Timeline")
    st.info("Timeline charts will be wired in a later patch.")

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

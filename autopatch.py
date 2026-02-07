from __future__ import annotations
import os, sys, subprocess, textwrap, re, json
from pathlib import Path
from datetime import datetime, timezone

DASH = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard")
RUNTIME = Path("/home/hackerman/agent-runtime")
PROPOSALS = RUNTIME / "planner" / "proposals"
WORK_ORDER = RUNTIME / "directives" / "priorities" / "dashboard_autobuild.md"
CHANGELOG = DASH / "CHANGELOG.md"
LOGS = RUNTIME / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def sh(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.stdout

def ensure_git():
    if not (DASH / ".git").exists():
        sh(["git", "init"], cwd=DASH)
        sh(["git", "add", "-A"], cwd=DASH)
        sh(["git", "commit", "-m", "init"], cwd=DASH)

def read_latest_outputs(n=6) -> str:
    if not PROPOSALS.exists():
        return "No proposals directory found."
    files = sorted(PROPOSALS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    chunks = []
    for p in files:
        try:
            chunks.append(f"FILE: {p.name}\n{p.read_text(encoding='utf-8')[:4000]}")
        except Exception as e:
            chunks.append(f"FILE: {p.name}\n<read error: {e}>")
    return "\n\n".join(chunks)

def extract_diff(text: str) -> str:
    # Accept typical unified diff markers
    m = re.search(r"(?s)(^diff --git .*|^--- .*?\n\+\+\+ .*?\n)", text, re.M)
    if not m:
        raise ValueError("No diff header found in model output.")
    return text[m.start():].strip()

def validate_diff(diff: str) -> None:
    # Only allow paths under the dashboard folder
    # Check diff --git a/<path> b/<path>
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                a = parts[2].removeprefix("a/")
                b = parts[3].removeprefix("b/")
                for p in (a, b):
                    if p == "/dev/null":
                        continue
                    # Disallow path traversal and absolute paths
                    if p.startswith("/") or ".." in Path(p).parts:
                        raise ValueError(f"Unsafe path in diff: {p}")
    # Additional protection: forbid edits outside repo by relying on git apply in repo
    # Also cap diff size
    if len(diff) > 250_000:
        raise ValueError("Diff too large; refusing.")

def call_ollama(prompt: str, model: str) -> str:
    import requests
    r = requests.post("http://127.0.0.1:11434/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=600)
    r.raise_for_status()
    return r.json().get("response","")

def main():
    model = os.environ.get("AUTOPATCH_MODEL", "qwen2.5-coder:7b")
    ensure_git()

    work = WORK_ORDER.read_text(encoding="utf-8") if WORK_ORDER.exists() else ""
    context = read_latest_outputs()

    instructions = f"""
You are an autonomous engineer improving a local Streamlit dashboard project.

Repository folder:
{DASH}

Hard rules:
- Output ONLY a unified diff (git style). No commentary.
- Only change files inside this repository (relative paths).
- Keep patches small and incremental.
- Prefer adding UX pages/tabs, summaries, timeline, and "Brief me" feature using Ollama.

Work order:
{work}

Recent agent outputs (for grounding):
{context}

Now produce the next patch.
""".strip()

    raw = call_ollama(instructions, model=model)
    diff = extract_diff(raw)
    validate_diff(diff)

    # Save diff artifact
    ts = utcnow().replace(":", "-")
    diff_path = LOGS / f"dashboard_patch_{ts}.diff"
    diff_path.write_text(diff, encoding="utf-8")

    # Apply diff
    sh(["git", "apply", "--whitespace=nowarn", str(diff_path)], cwd=DASH)

    # Smoke: import app
    # (don’t run server; just ensure syntax)
    sh([sys.executable, "-c", "import app"], cwd=DASH)

    # Changelog
    if not CHANGELOG.exists():
        CHANGELOG.write_text("# Changelog\n\n", encoding="utf-8")
    with CHANGELOG.open("a", encoding="utf-8") as f:
        f.write(f"## {utcnow()}\n- Applied patch: {diff_path.name}\n\n")

    # Commit
    sh(["git", "add", "-A"], cwd=DASH)
    sh(["git", "commit", "-m", f"autopatch {ts}"], cwd=DASH)

if __name__ == "__main__":
    main()

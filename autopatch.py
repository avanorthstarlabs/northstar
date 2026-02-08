from __future__ import annotations
import os, sys, subprocess, textwrap, re, json, shutil
from pathlib import Path
from datetime import datetime, timezone

DASH = Path("/home/hackerman/agent-runtime/workspace/projects/agent-dashboard")
RUNTIME = Path("/home/hackerman/agent-runtime")
PROPOSALS = RUNTIME / "planner" / "proposals"
WORK_ORDER = RUNTIME / "directives" / "priorities" / "dashboard_autobuild.md"
CHANGELOG = DASH / "CHANGELOG.md"
QUALITY_GATE = RUNTIME / "constitution" / "quality_gate.md"
LOGS = RUNTIME / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def sh(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.stdout

def check_apply(diff: str) -> None:
    p = subprocess.run(
        ["git", "apply", "--check", "--whitespace=nowarn", "-"],
        cwd=str(DASH),
        input=diff,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0:
        raise ValueError(f"git apply --check failed: {p.stdout.strip()}")

def detect_linter() -> list[str] | None:
    if shutil.which("ruff"):
        return ["ruff", "check", "app.py"]
    if shutil.which("flake8"):
        return ["flake8", "app.py"]
    return None

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
    if "```" in text:
        text = text.replace("```diff", "").replace("```", "")
    if "\ufeff" in text:
        text = text.replace("\ufeff", "")
    if "diff --git " in text:
        start = text.index("diff --git ")
        return text[start:].strip()
    stripped = text.lstrip()
    m = re.search(r"(?s)(^diff --git .*|^--- .*?\n\+\+\+ .*?\n)", stripped, re.M)
    if not m:
        raise ValueError("No diff header found in model output.")
    return stripped[m.start():].strip()

def normalize_hunks(diff: str) -> str:
    lines = diff.splitlines()
    out = []
    i = 0
    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            m = hunk_re.match(line)
            if not m:
                out.append(line)
                i += 1
                continue
            old_start = m.group(1)
            new_start = m.group(3)
            j = i + 1
            old_count = 0
            new_count = 0
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith("diff --git ") or nxt.startswith("@@"):
                    break
                if nxt.startswith("+") and not nxt.startswith("+++"):
                    new_count += 1
                elif nxt.startswith("-") and not nxt.startswith("---"):
                    old_count += 1
                else:
                    old_count += 1
                    new_count += 1
                j += 1
            out.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"

def validate_diff(diff: str) -> None:
    allowed_roots = {"app.py", "lib", "assets"}
    allowed_paths = set()
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
                    # Only allow updates within allowlist roots
                    root = Path(p).parts[0]
                    if root not in allowed_roots:
                        raise ValueError(f"Disallowed path in diff: {p}")
                    allowed_paths.add(p)
                # If this is a modification (not a new file), require that the file exists
                if a != "/dev/null" and b != "/dev/null":
                    target = DASH / b
                    if b == "CHANGELOG.md":
                        raise ValueError("Do not modify CHANGELOG.md in model diff; it is updated automatically.")
                    if not target.exists():
                        raise ValueError(f"Diff refers to missing file: {b}")
    # Additional protection: forbid edits outside repo by relying on git apply in repo
    # Also cap diff size
    if len(diff) > 250_000:
        raise ValueError("Diff too large; refusing.")

def call_ollama(prompt: str, model: str) -> str:
    import requests
    r = requests.post("http://127.0.0.1:11434/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=600)
    r.raise_for_status()
    return r.json().get("response","")

def call_openai(prompt: str, model: str) -> str:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)
    system = (
        "You are an autonomous code editor. "
        "Return ONLY a unified diff. "
        "The first line MUST start with: diff --git "
        "No markdown, no commentary, no extra text. "
        "Do NOT modify CHANGELOG.md; it is updated automatically. "
        "Keep changes small (aim for <= 120 lines changed)."
    )
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_output_tokens=4000,
    )
    text = ""
    try:
        text = resp.output_text
    except Exception:
        for o in getattr(resp, "output", []):
            for c in getattr(o, "content", []):
                if getattr(c, "type", None) in ("output_text", "text"):
                    text += getattr(c, "text", "")
    return text

def call_claude(prompt: str, model: str) -> str:
    from anthropic import Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=api_key)
    system = (
        "You are an autonomous code editor. "
        "Return ONLY a unified diff. "
        "The first line MUST start with: diff --git "
        "No markdown, no commentary, no extra text. "
        "Do NOT modify CHANGELOG.md; it is updated automatically. "
        "Keep changes small (aim for <= 120 lines changed)."
    )
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        temperature=0.2,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = ""
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            raw += block.text
    return raw

def main():
    model = os.environ.get("AUTOPATCH_MODEL", "qwen2.5-coder:7b")
    provider = os.environ.get("AUTOPATCH_PROVIDER", "ollama").strip().lower()
    ensure_git()
    if not CHANGELOG.exists():
        CHANGELOG.write_text("# Changelog\n\n", encoding="utf-8")

    work = WORK_ORDER.read_text(encoding="utf-8") if WORK_ORDER.exists() else ""
    context = read_latest_outputs()
    quality_gate = QUALITY_GATE.read_text(encoding="utf-8") if QUALITY_GATE.exists() else ""

    app_text = (DASH / "app.py").read_text(encoding="utf-8")

    # Keep prompt compact to reduce output truncation
    instructions = f"""
You are an autonomous engineer improving a local Streamlit dashboard project.

Repository folder:
{DASH}
Main app file: app.py (do not use main.py).

Hard rules:
- Output ONLY a unified diff (git style). No commentary.
- The first line MUST be: diff --git
- Do NOT modify CHANGELOG.md; it is updated automatically after the patch.
- Keep changes small (aim for <= 120 lines changed).
- Only change files inside this repository (relative paths).
- Keep patches small and incremental.
- Prefer adding UX pages/tabs, summaries, timeline, and "Brief me" feature using Ollama.

Current app.py (verbatim):
{app_text}

Work order:
{work}

General quality gate:
{quality_gate}

Now produce the next patch.
""".strip()

    raw = ""
    diff = ""
    last_err = ""
    for attempt in range(2):
        extra = "\nREMINDER: Output ONLY unified diff. No markdown. No commentary.\n" if attempt > 0 else ""
        prompt = instructions + extra
        if provider in ("codex", "openai"):
            raw = call_openai(prompt, model=model)
        elif provider == "claude":
            raw = call_claude(prompt, model=os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"))
        else:
            raw = call_ollama(prompt, model=model)
        try:
            diff = normalize_hunks(extract_diff(raw))
            validate_diff(diff)
            check_apply(diff)
            break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            diff = ""
            continue
    if not diff:
        ts = utcnow().replace(":", "-")
        raw_path = LOGS / f"dashboard_patch_raw_{ts}.txt"
        raw_path.write_text(raw, encoding="utf-8")
        raise ValueError(f"Model output did not contain a valid unified diff after retry ({last_err}). Raw saved to {raw_path.name}")

    # Save diff artifact
    ts = utcnow().replace(":", "-")
    diff_path = LOGS / f"dashboard_patch_{ts}.diff"
    diff_path.write_text(diff, encoding="utf-8")

    # Apply diff
    sh(["git", "apply", "--whitespace=nowarn", str(diff_path)], cwd=DASH)

    # Smoke: compile + import checks
    sh([sys.executable, "-m", "py_compile", "app.py"], cwd=DASH)
    sh([sys.executable, "-c", "import streamlit, app"], cwd=DASH)
    sh([sys.executable, "-c", "import app"], cwd=DASH)

    lint_cmd = detect_linter()
    if lint_cmd:
        sh(lint_cmd, cwd=DASH)

    # Changelog
    with CHANGELOG.open("a", encoding="utf-8") as f:
        f.write(f"## {utcnow()}\n- Applied patch: {diff_path.name}\n\n")

    # Commit
    sh(["git", "add", "-A"], cwd=DASH)
    sh(["git", "commit", "-m", f"autopatch {ts}"], cwd=DASH)

if __name__ == "__main__":
    main()

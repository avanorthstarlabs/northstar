from __future__ import annotations
import os, sys, subprocess, textwrap, re, json, shutil, difflib
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

def log_event(event: str, status: str, detail: str = "") -> None:
    try:
        line = json.dumps(
            {
                "ts": utcnow(),
                "event": event,
                "status": status,
                "detail": detail[:4000],
            }
        )
        (LOGS / "autopatch_events.jsonl").open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass

def safe_read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback

def sh(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.stdout

def apply_diff_file(path: Path) -> None:
    try:
        sh(["git", "apply", "--3way", "--whitespace=nowarn", str(path)], cwd=DASH)
    except subprocess.CalledProcessError:
        sh(["git", "apply", "--whitespace=nowarn", str(path)], cwd=DASH)

def check_apply(diff: str) -> None:
    p = subprocess.run(
        ["git", "apply", "--3way", "--check", "--whitespace=nowarn", "-"],
        cwd=str(DASH),
        input=diff,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0:
        p2 = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            cwd=str(DASH),
            input=diff,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if p2.returncode != 0:
            raise ValueError(f"git apply --check failed: {p2.stdout.strip()}")

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
        return ""
    return stripped[m.start():].strip()


def extract_fulltext(text: str) -> str:
    start = text.find("BEGIN_APP_PY")
    end = text.find("END_APP_PY")
    if start != -1 and end != -1 and end > start:
        return text[start + len("BEGIN_APP_PY"):end].strip("\n")
    return ""


def extract_diff_or_fulltext(text: str) -> tuple[str, str]:
    diff = extract_diff(text)
    if diff:
        return diff, ""
    fulltext = extract_fulltext(text)
    if fulltext:
        return "", fulltext
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            diff = data.get("diff") or data.get("patch") or ""
            if diff:
                return str(diff), ""
            fulltext = data.get("app_py") or data.get("app.py") or ""
            if fulltext:
                return "", str(fulltext)
    except Exception:
        pass
    return "", ""


def diff_from_fulltext(new_text: str, old_text: str) -> str:
    if new_text == old_text:
        return ""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="a/app.py",
        tofile="b/app.py",
        lineterm="",
    )
    return "\n".join(diff)

def sanitize_diff(diff: str) -> str:
    """Trim any trailing non-diff text that can corrupt git apply."""
    lines = diff.splitlines()
    allowed_prefixes = ("diff --git ", "index ", "--- ", "+++ ", "@@ ", "+", "-", " ", "\\")
    out = []
    for line in lines:
        if not out:
            if line.startswith("diff --git "):
                out.append(line)
            else:
                continue
            continue
        if line.startswith(allowed_prefixes):
            out.append(line)
        else:
            # Stop at first non-diff line after diff starts
            break
    return "\n".join(out).strip() + "\n"

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
    # No size cap; allow large cohesive UX overhaul diffs

def call_ollama(prompt: str, model: str) -> str:
    import requests
    r = requests.post("http://127.0.0.1:11434/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=600)
    r.raise_for_status()
    return r.json().get("response","")

def call_openai(prompt: str, model: str, max_output_tokens: int = 4000) -> str:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key, timeout=300)
    system = (
        "You are an autonomous code editor. "
        "Return ONLY a unified diff. "
        "The first line MUST start with: diff --git "
        "No markdown, no commentary, no extra text. "
        "Do NOT modify CHANGELOG.md; it is updated automatically. "
        "Do not worry about line-count limits; prioritize a cohesive UX overhaul."
    )
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_output_tokens=max_output_tokens,
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

def call_claude(prompt: str, model: str, max_tokens: int = 4000) -> str:
    from anthropic import Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=api_key, timeout=300)
    system = (
        "You are an autonomous code editor. "
        "Return ONLY a unified diff. "
        "The first line MUST start with: diff --git "
        "No markdown, no commentary, no extra text. "
        "Do NOT modify CHANGELOG.md; it is updated automatically. "
        "Do not worry about line-count limits; prioritize a cohesive UX overhaul."
    )
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
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
    model = os.environ.get("AUTOPATCH_MODEL", "gpt-5.2-codex")
    provider = os.environ.get("AUTOPATCH_PROVIDER", "ollama").strip().lower()
    max_out = int(os.environ.get("AUTOPATCH_MAX_TOKENS", "6000"))
    max_out_full = int(os.environ.get("AUTOPATCH_FULL_MAX_TOKENS", str(max_out * 2)))
    ensure_git()
    if not CHANGELOG.exists():
        CHANGELOG.write_text("# Changelog\n\n", encoding="utf-8")

    work = safe_read_text(WORK_ORDER)
    context = read_latest_outputs()
    quality_gate = safe_read_text(QUALITY_GATE)

    app_text = safe_read_text(DASH / "app.py")

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
- Only change files inside this repository (relative paths).
- This cycle is a deliberate UX overhaul: prioritize cohesive layout and visual structure over tiny tweaks.
- Make a single focused improvement (one or two sections). Avoid huge refactors in one cycle.
- Include enough context lines around changes so the patch applies cleanly.
If you cannot produce a diff, output the full contents of app.py only between:
BEGIN_APP_PY
...
END_APP_PY

Current app.py (verbatim):
{app_text}

Work order:
{work}

General quality gate:
{quality_gate}

Now produce the next patch.
""".strip()

    rewrite_instructions = f"""
You are an autonomous engineer improving a local Streamlit dashboard project.

Repository folder:
{DASH}
Main app file: app.py (do not use main.py).

Hard rules:
- Output ONLY a unified diff (git style). No commentary.
- The first line MUST be: diff --git
- Do NOT modify CHANGELOG.md; it is updated automatically after the patch.
- Only change files inside this repository (relative paths).
- OUTPUT A FULL FILE REPLACEMENT diff for app.py (delete and add the full file).
If you cannot produce a diff, output the full contents of app.py only between:
BEGIN_APP_PY
...
END_APP_PY

Current app.py (verbatim):
{app_text}

Work order:
{work}

General quality gate:
{quality_gate}

Now output a full replacement diff for app.py only.
""".strip()

    fulltext_instructions = f"""
You are an autonomous engineer improving a local Streamlit dashboard project.

Repository folder:
{DASH}
Main app file: app.py (do not use main.py).

Hard rules:
- Output ONLY the full contents of app.py.
- Wrap it between the exact markers:
BEGIN_APP_PY
...full file contents...
END_APP_PY
- Do NOT include a diff, markdown, or commentary.

Current app.py (verbatim):
{app_text}

Work order:
{work}

General quality gate:
{quality_gate}
""".strip()

    raw = ""
    diff = ""
    last_err = ""
    for attempt in range(3):
        extra = "\nREMINDER: Output ONLY unified diff. No markdown. No commentary.\n" if attempt > 0 else ""
        if attempt >= 2:
            extra += "\nIf you cannot output a diff, output FULL app.py between BEGIN_APP_PY and END_APP_PY.\n"
        prompt = instructions + extra
        try:
            if provider in ("codex", "openai"):
                raw = call_openai(prompt, model=model, max_output_tokens=max_out)
            elif provider == "claude":
                raw = call_claude(prompt, model=os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"), max_tokens=max_out)
            else:
                raw = call_ollama(prompt, model=model)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log_event("model_call", "error", last_err)
            continue
        try:
            diff, fulltext = extract_diff_or_fulltext(raw)
            if fulltext:
                old_text = (DASH / "app.py").read_text(encoding="utf-8")
                diff = diff_from_fulltext(fulltext, old_text)
            diff = normalize_hunks(sanitize_diff(diff))
            if not diff and fulltext:
                log_event("diff", "noop", "Fulltext produced no diff; skipping apply.")
                return
            validate_diff(diff)
            check_apply(diff)
            break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            diff = ""
            continue

    # Fallback: request full-file replacement if normal diff fails
    if not diff:
        try:
            fulltext = ""
            for ft_attempt in range(2):
                max_tokens = max_out_full if ft_attempt == 0 else int(max_out_full * 1.4)
                if provider in ("codex", "openai"):
                    raw = call_openai(fulltext_instructions, model=model, max_output_tokens=max_tokens)
                elif provider == "claude":
                    raw = call_claude(fulltext_instructions, model=os.environ.get("CLAUDE_MODEL", "claude-opus-4-6"), max_tokens=max_tokens)
                else:
                    raw = call_ollama(fulltext_instructions, model=model)
                fulltext = extract_fulltext(raw)
                if fulltext:
                    break
            if not fulltext:
                raise ValueError("No BEGIN_APP_PY/END_APP_PY block found in model output.")
            old_text = (DASH / "app.py").read_text(encoding="utf-8")
            diff = diff_from_fulltext(fulltext, old_text)
            diff = normalize_hunks(sanitize_diff(diff))
            if not diff:
                log_event("diff", "noop", "Fulltext produced no diff; skipping apply.")
                return
            validate_diff(diff)
            check_apply(diff)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            diff = ""
    if not diff:
        ts = utcnow().replace(":", "-")
        raw_path = LOGS / f"dashboard_patch_raw_{ts}.txt"
        raw_path.write_text(raw, encoding="utf-8")
        log_event("diff", "error", f"Invalid diff after retries: {last_err}")
        raise ValueError(f"Model output did not contain a valid unified diff after retry ({last_err}). Raw saved to {raw_path.name}")

    # Save diff artifact
    ts = utcnow().replace(":", "-")
    diff_path = LOGS / f"dashboard_patch_{ts}.diff"
    diff_path.write_text(diff, encoding="utf-8")

    # Apply diff (3-way to reduce patch drift failures)
    apply_diff_file(diff_path)

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

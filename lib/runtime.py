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

def list_matching(patterns: list[str]) -> list[Path]:
    if not PROPOSALS_DIR.exists():
        return []
    items: list[Path] = []
    for pattern in patterns:
        items.extend(PROPOSALS_DIR.glob(pattern))
    return sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)

def stat_mtime_iso(p: Path) -> str:
    ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return ts.isoformat()

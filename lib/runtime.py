from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import re

RUNTIME = Path("/home/hackerman/agent-runtime")
MODE_FILE = RUNTIME / "constitution" / "mode.state"
INBOX_FILE = RUNTIME / "directives" / "priorities" / "00_inbox.md"
TRIGGER_FILE = RUNTIME / "directives" / "priorities" / ".trigger"
PROPOSALS_DIR = RUNTIME / "planner" / "proposals"
DECISIONS_DIR = RUNTIME / "planner" / "decisions"
PRIORITIES_DIR = RUNTIME / "directives" / "priorities"
APPROVED_DIR = PRIORITIES_DIR / "approved"

# Centralized proposal/review file patterns (keep in sync with UI expectations)
PROPOSAL_PATTERNS = [
    "claude_*.json",
    "openai_*.json",
    "local_*.json",
    "codex_*.json",
    "proposal_*.json",
]
REVIEW_PATTERNS = [
    "review_*__by_*.json",
]

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

def _slugify(value: str, fallback: str = "proposal") -> str:
    if not value:
        return fallback
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return (slug or fallback)[:80]

def _decision_path(proposal_path: Path) -> Path:
    _ensure_parent(DECISIONS_DIR / "placeholder")
    return DECISIONS_DIR / f"decision_{proposal_path.stem}.json"

def read_decision(proposal_path: Path) -> dict | None:
    path = _decision_path(proposal_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def write_decision(proposal_path: Path, decision: str, note: str = "", source: str = "dashboard", extra: dict | None = None) -> Path:
    decision = decision.strip().upper()
    payload = {
        "proposal_path": str(proposal_path),
        "proposal_id": proposal_path.stem,
        "decision": decision,
        "note": note,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    path = _decision_path(proposal_path)
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path

def write_priority_from_proposal(proposal_path: Path, proposal_obj: dict, note: str = "") -> Path:
    _ensure_parent(APPROVED_DIR / "placeholder")
    proposal_id = str(proposal_obj.get("proposal_id") or proposal_path.stem)
    slug = _slugify(proposal_id, fallback=_slugify(proposal_path.stem))
    out = APPROVED_DIR / f"approved_{slug}.md"

    summary = str(proposal_obj.get("summary") or "").strip()
    context = str(proposal_obj.get("context") or "").strip()
    reasoning = str(proposal_obj.get("reasoning") or "").strip()
    mode = str(proposal_obj.get("mode") or "").strip()
    confidence = proposal_obj.get("confidence")
    suggested = proposal_obj.get("suggested_actions") or []
    success = proposal_obj.get("success_criteria") or []

    if not isinstance(suggested, list):
        suggested = [str(suggested)]
    if not isinstance(success, list):
        success = [str(success)]

    lines = [
        f"# Approved Proposal: {summary or proposal_id}",
        "",
        "## Metadata",
        f"- Proposal ID: {proposal_id}",
        f"- Proposal File: {proposal_path}",
        f"- Mode: {mode or '—'}",
        f"- Confidence: {confidence if confidence is not None else '—'}",
        f"- Approved At: {datetime.now(timezone.utc).isoformat()}",
    ]
    if note:
        lines += ["- Approval Note: " + note]
    lines += [
        "",
        "## Summary",
        summary or "—",
        "",
        "## Context",
        context or "—",
        "",
        "## Reasoning",
        reasoning or "—",
        "",
        "## Suggested Actions",
    ]
    lines += [f"- {item}" for item in suggested] if suggested else ["- —"]
    lines += [
        "",
        "## Success Criteria",
    ]
    lines += [f"- {item}" for item in success] if success else ["- —"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out

def promote_priority(approved_path: Path) -> Path:
    _ensure_parent(PRIORITIES_DIR / "placeholder")
    if not approved_path.exists():
        raise FileNotFoundError(str(approved_path))
    name = approved_path.name
    if name.startswith("approved_"):
        name = name.replace("approved_", "", 1)
    target = PRIORITIES_DIR / name
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = PRIORITIES_DIR / f"{target.stem}_{stamp}{target.suffix}"
    approved_path.replace(target)
    return target

def _latest_matching(prefix: str) -> Path | None:
    if not PROPOSALS_DIR.exists():
        return None
    files = sorted(PROPOSALS_DIR.glob(prefix), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _latest_matching_any(patterns: list[str]) -> Path | None:
    if not PROPOSALS_DIR.exists():
        return None
    items: list[Path] = []
    for pattern in patterns:
        items.extend(PROPOSALS_DIR.glob(pattern))
    items = sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0] if items else None

def latest_claude() -> Path | None:
    return _latest_matching("claude_*.json")

def latest_review() -> Path | None:
    return _latest_matching("review_claude_*__by_openai.json")

def proposal_patterns() -> list[str]:
    return list(PROPOSAL_PATTERNS)

def review_patterns() -> list[str]:
    return list(REVIEW_PATTERNS)

def output_patterns() -> list[str]:
    return list(PROPOSAL_PATTERNS) + list(REVIEW_PATTERNS)

def latest_proposal_any() -> Path | None:
    return _latest_matching_any(proposal_patterns())

def latest_review_any() -> Path | None:
    return _latest_matching_any(review_patterns())

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

def extract_timestamp(p: Path) -> datetime:
    try:
        data = read_json_file(p)
    except Exception:
        data = None
    if isinstance(data, dict):
        for key in ("timestamp", "created_at", "createdAt", "created", "ts", "time", "date"):
            if key in data:
                dt = _parse_timestamp_value(data.get(key))
                if dt:
                    return dt
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)

def _parse_timestamp_value(value) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None

from __future__ import annotations

import json
import os
import subprocess


OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "/home/hackerman/.openclaw/bin/openclaw")
OPENCLAW_AGENT = os.environ.get("OPENCLAW_AGENT", "main")


def _extract_json(s: str) -> dict:
    s = (s or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1].strip() if len(parts) >= 3 else s.replace("```", "").strip()
    if s.startswith("{") and s.endswith("}"):
        return json.loads(s)
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(s[start:end+1])
    raise ValueError("No JSON object found in OpenClaw output.")


def _extract_text(obj: dict) -> str:
    payloads = obj.get("payloads")
    if isinstance(payloads, list):
        for payload in payloads:
            if isinstance(payload, dict) and isinstance(payload.get("text"), str) and payload["text"].strip():
                return payload["text"]
    for key in ("reply", "message", "output", "text", "content", "response"):
        if isinstance(obj.get(key), str) and obj[key].strip():
            return obj[key]
    raise ValueError("No reply text found in OpenClaw output.")


def _run(prompt: str, timeout: int = 90) -> str:
    cmd = [
        OPENCLAW_BIN,
        "agent",
        "--local",
        "--agent", OPENCLAW_AGENT,
        "--json",
        "--timeout", str(timeout),
        "--message", prompt,
    ]
    result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        raise RuntimeError(err or f"OpenClaw failed with code {result.returncode}")
    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError("OpenClaw returned empty output.")
    return _extract_text(_extract_json(raw))


def generate(model: str, prompt: str, timeout: int = 90, max_output_tokens: int | None = None) -> str:
    # model/max_output_tokens are ignored here; OpenClaw uses the configured local model.
    return _run(prompt, timeout=timeout)


def chat(model: str, prompt: str, timeout: int = 90, max_output_tokens: int | None = None) -> str:
    return _run(prompt, timeout=timeout)

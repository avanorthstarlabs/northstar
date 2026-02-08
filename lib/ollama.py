from __future__ import annotations
import requests

OLLAMA = "http://127.0.0.1:11434"

def list_models(timeout: int = 10) -> list[str]:
    # /api/tags returns {"models":[{"name":"..."}]}
    r = requests.get(f"{OLLAMA}/api/tags", timeout=timeout)
    r.raise_for_status()
    j = r.json()
    models = [m.get("name") for m in j.get("models", []) if m.get("name")]
    return models

def chat(model: str, prompt: str, timeout: int = 120) -> str:
    # Use generate endpoint; stream=false for simplicity
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = requests.post(f"{OLLAMA}/api/generate", json=payload, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    return j.get("response", "")

def generate(model: str, prompt: str, timeout: int = 120) -> str:
    # Same endpoint as chat, but used for one-shot summaries
    return chat(model, prompt, timeout=timeout)

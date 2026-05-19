"""
ollama_client.py
================
Small Ollama chat wrapper with strict JSON-array extraction for planners.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from core.settings import (
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_RETRIES,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SECONDS,
)

_SESSION = requests.Session()


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = fenced.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Model output is not a JSON object.")
    return parsed


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[[\s\S]*\])\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = fenced.group(1)
    else:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]

    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Model output is not a JSON array.")
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Planner JSON array must contain objects.")
    return parsed


def _model_matches(installed_name: str, requested_name: str) -> bool:
    installed = (installed_name or "").strip().lower()
    requested = (requested_name or "").strip().lower()
    if not installed or not requested:
        return False
    if installed == requested:
        return True
    # Ollama tags may default to :latest.
    if ":" not in requested and installed == f"{requested}:latest":
        return True
    if ":" in requested and requested.endswith(":latest") and installed == requested.split(":")[0]:
        return True
    return False


def ensure_ollama_model_ready(
    *,
    pull_if_missing: bool = True,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    base = OLLAMA_BASE_URL.rstrip("/")
    tags_url = f"{base}/api/tags"
    tags_resp = _SESSION.get(tags_url, timeout=20)
    tags_resp.raise_for_status()
    models = ((tags_resp.json() or {}).get("models") or [])
    installed_names = [m.get("name", "") for m in models if isinstance(m, dict)]
    if any(_model_matches(name, OLLAMA_MODEL) for name in installed_names):
        return {"ok": True, "model": OLLAMA_MODEL, "pulled": False, "message": "Model already available."}

    if not pull_if_missing:
        return {"ok": False, "model": OLLAMA_MODEL, "pulled": False, "message": "Model not installed in Ollama."}

    pull_url = f"{base}/api/pull"
    pull_resp = _SESSION.post(
        pull_url,
        json={"name": OLLAMA_MODEL, "stream": False},
        timeout=max(timeout_seconds, 30),
    )
    pull_resp.raise_for_status()
    return {"ok": True, "model": OLLAMA_MODEL, "pulled": True, "message": "Model pulled and ready."}


def call_ollama_json_plan(
    *,
    user_query: str,
    system_prompt: str,
    retries: int | None = None,
) -> list[dict[str, Any]]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    options: dict[str, Any] = {"temperature": OLLAMA_TEMPERATURE}
    if OLLAMA_NUM_PREDICT > 0:
        options["num_predict"] = OLLAMA_NUM_PREDICT
    if OLLAMA_NUM_CTX > 0:
        options["num_ctx"] = OLLAMA_NUM_CTX

    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        "stream": False,
        "options": options,
        "keep_alive": OLLAMA_KEEP_ALIVE.strip() or "15m",
    }
    last_error: Exception | None = None
    max_retries = OLLAMA_RETRIES if retries is None else max(retries, 0)
    for _ in range(max_retries + 1):
        try:
            response = _SESSION.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
            response.raise_for_status()
            body = response.json()
            content = ((body.get("message") or {}).get("content") or "").strip()
            return _extract_json_array(content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"Ollama planner call failed: {last_error}") from last_error


def call_ollama_json_object(
    *,
    user_query: str,
    system_prompt: str,
    num_predict: int | None = None,
    timeout_seconds: int | None = None,
    retries: int | None = None,
) -> dict[str, Any]:
    """
    Single JSON object response (used for validated analytic plans, not planner steps).
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    options: dict[str, Any] = {"temperature": OLLAMA_TEMPERATURE}
    predict = OLLAMA_NUM_PREDICT if num_predict is None else num_predict
    if predict > 0:
        options["num_predict"] = predict
    if OLLAMA_NUM_CTX > 0:
        options["num_ctx"] = OLLAMA_NUM_CTX

    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        "stream": False,
        "options": options,
        "keep_alive": OLLAMA_KEEP_ALIVE.strip() or "15m",
    }
    last_error: Exception | None = None
    max_retries = OLLAMA_RETRIES if retries is None else max(retries, 0)
    timeout = OLLAMA_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    for _ in range(max_retries + 1):
        try:
            response = _SESSION.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
            content = ((body.get("message") or {}).get("content") or "").strip()
            return _extract_json_object(content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"Ollama JSON object call failed: {last_error}") from last_error

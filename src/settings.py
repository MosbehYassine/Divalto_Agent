"""
Runtime settings loaded from environment variables.

This keeps credentials/endpoints out of source code and makes
dev/preprod/prod switching easier.
"""

import os
from pathlib import Path


def _load_dotenv_if_present() -> None:
    """
    Minimal .env loader to avoid hard runtime dependencies.
    Only sets variables that are not already present in environment.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present()


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value if value else default


def _get_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


BASE_URL = _get_env("DIVALTO_BASE_URL", "https://your-divalto-server.com")
AUTH_URL = _get_env("DIVALTO_AUTH_URL", f"{BASE_URL}/auth")
WS_URL = _get_env("DIVALTO_WS_URL", f"{BASE_URL}/webservice")

CREDENTIALS = {
    "user": _get_env("DIVALTO_USER", "Infolib"),
    "password": _get_env("DIVALTO_PASSWORD", "LibInfo"),
    "env": _get_env("DIVALTO_ENV", "ERP221"),
}

DOSSIER_CODE = _get_env("DIVALTO_DOSSIER_CODE", "998")

# HTTP/runtime tuning
AUTH_TIMEOUT_SECONDS = int(_get_env("DIVALTO_AUTH_TIMEOUT_SECONDS", "10"))
WS_TIMEOUT_SECONDS = int(_get_env("DIVALTO_WS_TIMEOUT_SECONDS", "15"))
HTTP_MAX_RETRIES = int(_get_env("DIVALTO_HTTP_MAX_RETRIES", "3"))
AUTH_TOKEN_TTL_SECONDS = int(_get_env("DIVALTO_AUTH_TOKEN_TTL_SECONDS", "3600"))

# Optional local sqlite backend for no-endpoint integration tests.
USE_SQLITE_MOCK = _get_bool_env("DIVALTO_USE_SQLITE_MOCK", False)
SQLITE_MOCK_DB_PATH = _get_env("DIVALTO_SQLITE_DB_PATH", "")

# ── Phase 6 — governance / audit ─────────────────────────────────────────────
GOVERNANCE_ENABLED = _get_bool_env("DIVALTO_GOVERNANCE_ENABLED", False)
HITL_ENFORCE = _get_bool_env("DIVALTO_HITL_ENFORCE", False)
AUDIT_JSONL_PATH = _get_env("DIVALTO_AUDIT_JSONL_PATH", "")
ALLOWED_WS_ACTIONS = _get_env("DIVALTO_ALLOWED_WS_ACTIONS", "")
DENIED_WS_ACTIONS = _get_env("DIVALTO_DENIED_WS_ACTIONS", "")
IRREVERSIBLE_WS_ACTIONS = _get_env("DIVALTO_IRREVERSIBLE_WS_ACTIONS", "integrer_piece")
STRATEGIC_CUSTOMERS_CSV = _get_env("DIVALTO_STRATEGIC_CUSTOMERS", "")
try:
    INVOICE_HITL_THRESHOLD_EUR = float(_get_env("DIVALTO_INVOICE_HITL_THRESHOLD_EUR", "50000"))
except ValueError:
    INVOICE_HITL_THRESHOLD_EUR = 50_000.0

# ── Full auto OLAP refresh ───────────────────────────────────────────────────
AUTO_OLAP_REFRESH_ENABLED = _get_bool_env("DIVALTO_AUTO_OLAP_REFRESH_ENABLED", True)
AUTO_OLAP_FORCE_REFRESH = _get_bool_env("DIVALTO_AUTO_OLAP_FORCE_REFRESH", False)
AUTO_OLAP_PROCESS_SSAS = _get_bool_env("DIVALTO_AUTO_OLAP_PROCESS_SSAS", False)
AUTO_OLAP_SSAS_COMMAND = _get_env("DIVALTO_AUTO_OLAP_SSAS_COMMAND", "")
AUTO_OLAP_ASYNC_REFRESH = _get_bool_env("DIVALTO_AUTO_OLAP_ASYNC_REFRESH", True)

# ── LLM / Ollama integration ─────────────────────────────────────────────────
OLLAMA_BASE_URL = _get_env("DIVALTO_OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _get_env("DIVALTO_OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")
# Planner JSON is short; tight timeouts + few retries → fast fallback to rule-based planner.
OLLAMA_TIMEOUT_SECONDS = int(_get_env("DIVALTO_OLLAMA_TIMEOUT_SECONDS", "45"))
OLLAMA_TEMPERATURE = float(_get_env("DIVALTO_OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_RETRIES = int(_get_env("DIVALTO_OLLAMA_RETRIES", "1"))
# Cap generation length (planner output is a small JSON array).
OLLAMA_NUM_PREDICT = int(_get_env("DIVALTO_OLLAMA_NUM_PREDICT", "512"))
# Smaller context window = less KV cache work on CPU; raise if planner misses constraints.
OLLAMA_NUM_CTX = int(_get_env("DIVALTO_OLLAMA_NUM_CTX", "4096"))
# Keep model loaded between chat calls to avoid cold reload latency (Ollama duration string).
OLLAMA_KEEP_ALIVE = _get_env("DIVALTO_OLLAMA_KEEP_ALIVE", "15m")
# Hard cap for Phase 3/5 JSON planner calls (Ollama); on timeout, rule-based mock_plan is used.
try:
    LLM_PLAN_TIMEOUT_SECONDS = float(_get_env("DIVALTO_LLM_PLAN_TIMEOUT_SECONDS", "25"))
except ValueError:
    LLM_PLAN_TIMEOUT_SECONDS = 25.0

# ── RAG retrieval layer ───────────────────────────────────────────────────────
RAG_ENABLED = _get_bool_env("DIVALTO_RAG_ENABLED", True)
RAG_DOCS_DIR = _get_env("DIVALTO_RAG_DOCS_DIR", "")
RAG_TOP_K = int(_get_env("DIVALTO_RAG_TOP_K", "3"))
RAG_CHUNK_SIZE = int(_get_env("DIVALTO_RAG_CHUNK_SIZE", "900"))
RAG_FILE_EXTENSIONS = _get_env("DIVALTO_RAG_FILE_EXTENSIONS", ".md,.txt,.json")
PLANNER_PROMPT_TEMPLATES_PATH = _get_env("DIVALTO_PLANNER_PROMPT_TEMPLATES_PATH", "")

# ── Semantic analytics / MDX (Phase 4 data questions) ─────────────────────────
# Directory containing semantic_model.json (+ optional mdx_templates.json) from auto_olap_pipeline.
SEMANTIC_MODEL_DIR = _get_env("DIVALTO_SEMANTIC_MODEL_DIR", "")
OLAP_CUBE_NAME = _get_env("DIVALTO_OLAP_CUBE_NAME", "AutoCube")
# When true, missing semantic_model.json is generated from DIVALTO_SQLITE_DB_PATH via auto_olap_pipeline.
AUTO_GENERATE_SEMANTIC_FROM_SQLITE = _get_bool_env("DIVALTO_AUTO_GENERATE_SEMANTIC_FROM_SQLITE", True)
OLLAMA_ANALYTIC_NUM_PREDICT = int(_get_env("DIVALTO_OLLAMA_ANALYTIC_NUM_PREDICT", "2048"))
OLLAMA_ANALYTIC_TIMEOUT_SECONDS = int(_get_env("DIVALTO_OLLAMA_ANALYTIC_TIMEOUT_SECONDS", "120"))

# Remote MDX (optional; see requirements-olap.txt)
MDX_CONNECTION_STRING = _get_env("DIVALTO_MDX_CONNECTION_STRING", "")
MDX_EXECUTE_ENABLED = _get_bool_env("DIVALTO_MDX_EXECUTE_ENABLED", False)
SEMANTIC_ANALYTICS_IN_CLASSIC = _get_bool_env("DIVALTO_SEMANTIC_ANALYTICS_IN_CLASSIC", True)

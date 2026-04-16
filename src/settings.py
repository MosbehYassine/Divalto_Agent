"""
Runtime settings loaded from environment variables.

This keeps credentials/endpoints out of source code and makes
dev/preprod/prod switching easier.
"""

import os


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value if value else default


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

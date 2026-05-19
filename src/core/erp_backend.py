"""
erp_backend.py
================
Dependency-inversion layer for ERP / mock data access (SOLID — DIP + LSP).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.settings import USE_SQLITE_MOCK


@runtime_checkable
class ErpBackend(Protocol):
    """Execute a validated webservice action and return raw ERP JSON."""

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class SqliteErpBackend:
    """Local SQLite implementation of the WS contract."""

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        from core.sqlite_backend import execute_action
        from core.settings import SQLITE_MOCK_DB_PATH

        return execute_action(action, dict(payload), SQLITE_MOCK_DB_PATH or None)


class DivaltoHttpErpBackend:
    """HTTP Divalto webservice implementation."""

    def __init__(self, token: str) -> None:
        self._token = token

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        from core.divalto_agent import call_webservice_details

        body = dict(payload)
        body["action"] = action
        result = call_webservice_details(self._token, body)
        if result.get("ok"):
            data = result.get("data")
            return data if isinstance(data, dict) else {}
        error = result.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(message or f"Webservice call failed for action '{action}'")


def get_erp_backend(token: str = "") -> ErpBackend:
    """Factory: mock SQLite vs live Divalto based on settings."""
    if USE_SQLITE_MOCK:
        return SqliteErpBackend()
    return DivaltoHttpErpBackend(token)

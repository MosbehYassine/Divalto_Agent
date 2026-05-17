"""
phase4_tools.py
===============
Phase 4 tool registry generated from WS schemas + semantic catalog.
"""

from dataclasses import dataclass
from typing import Any

from divalto_agent import WS_SCHEMAS
from semantic_router import get_action_metadata


@dataclass(frozen=True)
class WSTool:
    tool_name: str
    action: str
    description: str
    domain: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]


def _build_tool_description(action: str, domain: str) -> str:
    return f"Auto-discovered WS action '{action}' in domain '{domain}'."


def _build_registry() -> dict[str, WSTool]:
    registry: dict[str, WSTool] = {}
    for action, schema in WS_SCHEMAS.items():
        meta = get_action_metadata(action)
        tool_name = meta["tool_name"]
        # Keep registry key unique even if multiple actions share a tool label.
        key = tool_name if tool_name not in registry else f"{tool_name}__{action}"
        registry[key] = WSTool(
            tool_name=tool_name,
            action=action,
            description=_build_tool_description(action, meta["domain"]),
            domain=meta["domain"],
            required_fields=tuple(schema.get("required", [])),
            optional_fields=tuple(schema.get("optional", {}).keys()),
        )
    return registry


TOOLS_REGISTRY: dict[str, WSTool] = _build_registry()


def list_tools() -> list[dict[str, Any]]:
    """
    Return registry entries in JSON-serializable form.
    """
    return [
        {
            "tool_name": tool.tool_name,
            "action": tool.action,
            "description": tool.description,
            "domain": tool.domain,
            "required_fields": list(tool.required_fields),
            "optional_fields": list(tool.optional_fields),
        }
        for tool in TOOLS_REGISTRY.values()
    ]


def get_tool_by_action(action: str) -> WSTool | None:
    """
    Resolve registry entry from WS action name.
    """
    for tool in TOOLS_REGISTRY.values():
        if tool.action == action:
            return tool
    return None

from typing import Any


class ToolRouter:
    """Policy helper for runtime tool events.

    Hermes stays autonomous. This router only classifies events so the platform
    can normalize risk and route permission requests through backend approvals.
    """

    HIGH_RISK_KINDS = {"execute", "edit", "delete", "move"}

    def risk_for_tool(self, tool_call: dict[str, Any]) -> str:
        kind = str(tool_call.get("kind") or "").lower()
        return "high" if kind in self.HIGH_RISK_KINDS else "medium"

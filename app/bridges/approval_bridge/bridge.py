import asyncio
from typing import Any

from app.config import APPROVAL_POLL_SECONDS, APPROVAL_TIMEOUT_SECONDS
from app.runs.context import AgentContext


class ApprovalBridge:
    def __init__(self, context: AgentContext) -> None:
        self.context = context

    async def request_permission(self, action: str, risk: str, payload: dict[str, Any] | None = None) -> bool:
        approval = await self.context.backend.create_approval(
            self.context.task.id,
            action=action,
            risk=risk,
            payload=payload,
        )
        approval_id = approval["id"]
        deadline = asyncio.get_running_loop().time() + APPROVAL_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            current = await self.context.backend.get_approval(approval_id)
            status = current.get("status")
            if status == "approved":
                return True
            if status == "rejected":
                return False
            await asyncio.sleep(APPROVAL_POLL_SECONDS)
        return False

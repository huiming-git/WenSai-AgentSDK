from typing import Any

from app.runs.context import AgentContext


class EventEmitter:
    def __init__(self, context: AgentContext) -> None:
        self.context = context

    async def emit(
        self,
        event_type: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.context.backend.emit_event(
            self.context.task.id,
            event_type=event_type,
            content=content,
            metadata=metadata,
        )

    async def thinking(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        await self.emit("agent_thinking", content, metadata)

    async def message(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        await self.emit("agent_message", content, metadata)

    async def tool_started(self, tool: str, metadata: dict[str, Any] | None = None) -> None:
        await self.emit("tool_call_started", f"调用工具：{tool}", {"tool": tool, **(metadata or {})})

    async def tool_finished(self, tool: str, metadata: dict[str, Any] | None = None) -> None:
        await self.emit("tool_call_finished", "工具调用完成", {"tool": tool, **(metadata or {})})

    async def file_created(self, filename: str, metadata: dict[str, Any] | None = None) -> None:
        await self.emit("file_created", filename, {"filename": filename, **(metadata or {})})

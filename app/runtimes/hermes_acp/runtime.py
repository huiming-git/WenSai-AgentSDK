from typing import Any

from app.bridges.approval_bridge.bridge import ApprovalBridge
from app.bridges.event_bridge.emitter import EventEmitter
from app.runtimes.base import AgentRuntime
from app.runtimes.hermes_acp.client import HermesACPClient
from app.runtimes.hermes_acp.event_mapper import ACPEventMapper
from app.runs.context import AgentContext
from app.runs.schemas import RuntimeResult
from app.runtimes.tools.router import ToolRouter


class HermesACPRuntime(AgentRuntime):
    async def run(self, context: AgentContext) -> RuntimeResult:
        emitter = EventEmitter(context)
        mapper = ACPEventMapper()
        chunk_buffer = ACPChunkEventBuffer(emitter)
        approvals = ApprovalBridge(context)
        tool_router = ToolRouter()

        async def on_event(method: str, params: dict[str, Any]) -> None:
            event_type, content, metadata = mapper.map_update(params)
            await chunk_buffer.handle(event_type, content, metadata)

        async def on_permission(params: dict[str, Any]) -> bool:
            tool_call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
            action = str(tool_call.get("title") or tool_call.get("toolCallId") or "Agent permission request")
            risk = tool_router.risk_for_tool(tool_call)
            return await approvals.request_permission(action=action, risk=risk, payload=params)

        await emitter.emit("agent_runtime_started", "Hermes ACP runtime started", {"runtime": "hermes_acp"})
        async with HermesACPClient(
            cwd=str(context.workspace_dir),
            on_event=on_event,
            on_permission=on_permission,
        ) as client:
            output_text, metadata = await client.prompt_once(build_sandbox_prompt(context))

        await chunk_buffer.flush()
        await emitter.emit("agent_runtime_stopped", "Hermes ACP runtime finished", {"runtime": "hermes_acp"})
        return RuntimeResult(output_text=output_text, metadata=metadata)


def build_sandbox_prompt(context: AgentContext) -> str:
    return "\n".join(
        [
            "你正在 WenSai 任务沙盒内执行任务。",
            f"当前沙盒目录：{context.workspace_dir}",
            "只能在当前沙盒目录内读取任务输入、创建文件、修改文件和运行命令。",
            "输入文件位于 input/，最终结果和新增产物请写入 output/。",
            "",
            context.task.prompt,
        ]
    )


class ACPChunkEventBuffer:
    """Coalesce Hermes ACP text chunks into one WenSai event per ACP message."""

    CHUNK_TYPES = {"agent_thinking", "agent_message"}

    def __init__(self, emitter: EventEmitter) -> None:
        self.emitter = emitter
        self.event_type: str | None = None
        self.message_id: str | None = None
        self.parts: list[str] = []
        self.metadata: dict[str, Any] | None = None
        self.chunk_count = 0

    async def handle(self, event_type: str, content: str | None, metadata: dict[str, Any] | None) -> None:
        if self._is_chunk_event(event_type, metadata):
            message_id = self._message_id(metadata)
            if self.event_type != event_type or self.message_id != message_id:
                await self.flush()
            self.event_type = event_type
            self.message_id = message_id
            self.parts.append(content or "")
            self.metadata = self._merge_metadata(self.metadata, metadata)
            self.chunk_count += 1
            return

        await self.flush()
        await self.emitter.emit(event_type, content=content, metadata=metadata)

    async def flush(self) -> None:
        if self.event_type is None:
            return

        content = "".join(self.parts).strip()
        metadata = dict(self.metadata or {})
        metadata["chunk_count"] = self.chunk_count
        metadata["coalesced"] = True
        await self.emitter.emit(self.event_type, content=content or None, metadata=metadata)
        self.event_type = None
        self.message_id = None
        self.parts = []
        self.metadata = None
        self.chunk_count = 0

    def _is_chunk_event(self, event_type: str, metadata: dict[str, Any] | None) -> bool:
        raw_type = (metadata or {}).get("raw_type")
        return event_type in self.CHUNK_TYPES and raw_type in {"agent_thought_chunk", "agent_message_chunk"}

    def _message_id(self, metadata: dict[str, Any] | None) -> str | None:
        raw_event = (metadata or {}).get("raw_event")
        if not isinstance(raw_event, dict):
            return None
        value = raw_event.get("messageId") or raw_event.get("message_id")
        return str(value) if value is not None else None

    def _merge_metadata(self, current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any] | None:
        if incoming is None:
            return current
        if current is None:
            return dict(incoming)
        merged = dict(current)
        merged["raw_event"] = incoming.get("raw_event", merged.get("raw_event"))
        return merged

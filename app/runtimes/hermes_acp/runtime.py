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
        approvals = ApprovalBridge(context)
        tool_router = ToolRouter()

        async def on_event(method: str, params: dict[str, Any]) -> None:
            event_type, content, metadata = mapper.map_update(params)
            await emitter.emit(event_type, content=content, metadata=metadata)

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

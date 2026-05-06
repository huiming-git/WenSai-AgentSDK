from typing import Any


class ACPEventMapper:
    def map_update(self, params: dict[str, Any]) -> tuple[str, str | None, dict[str, Any] | None]:
        update = params.get("update") if isinstance(params.get("update"), dict) else {}
        kind = update.get("sessionUpdate")
        metadata = {"source": "hermes_acp", "raw_type": kind, "raw_event": update}

        if kind == "agent_message_chunk":
            content = update.get("content") if isinstance(update.get("content"), dict) else {}
            return "agent_message", content.get("text"), metadata

        if kind == "agent_thought_chunk":
            content = update.get("content") if isinstance(update.get("content"), dict) else {}
            return "agent_thinking", content.get("text"), metadata

        if kind in {"tool_call", "tool_call_update"}:
            tool = update.get("title") or update.get("toolCallId") or "tool"
            metadata["tool"] = tool
            return "tool_call_started", f"调用工具：{tool}", metadata

        if kind == "available_commands_update":
            return "agent_thinking", "可用命令已更新", metadata

        return "agent_thinking", kind or "Hermes ACP event", metadata

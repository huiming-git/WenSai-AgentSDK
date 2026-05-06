from __future__ import annotations

import asyncio
import logging
import shutil
import shlex
from pathlib import Path
from typing import Any, Awaitable, Callable

from acp import PROTOCOL_VERSION, spawn_agent_process
from acp.schema import (
    AllowedOutcome,
    ClientCapabilities,
    CreateTerminalResponse,
    DeniedOutcome,
    Implementation,
    KillTerminalResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalOutputResponse,
    TextContentBlock,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

from app.config import BWRAP_COMMAND, HERMES_ACP_ARGS, HERMES_ACP_COMMAND, HERMES_ACP_TIMEOUT_SECONDS, LOCAL_SANDBOX_ENFORCE_PROCESS

logger = logging.getLogger(__name__)

PermissionCallback = Callable[[dict[str, Any]], Awaitable[bool]]
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class _WenSaiACPClient:
    def __init__(
        self,
        on_event: EventCallback | None = None,
        on_permission: PermissionCallback | None = None,
    ) -> None:
        self.on_event = on_event
        self.on_permission = on_permission
        self.message_chunks: list[str] = []

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        payload = update.model_dump(by_alias=True) if hasattr(update, "model_dump") else dict(update)
        content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
        if payload.get("sessionUpdate") == "agent_message_chunk" and content.get("type") == "text":
            self.message_chunks.append(str(content.get("text") or ""))
        if self.on_event:
            await self.on_event("session/update", {"sessionId": session_id, "update": payload, **kwargs})

    async def request_permission(self, options: list[Any], session_id: str, tool_call: Any, **kwargs: Any) -> RequestPermissionResponse:
        tool_payload = tool_call.model_dump(by_alias=True) if hasattr(tool_call, "model_dump") else dict(tool_call)
        option_payloads = [option.model_dump(by_alias=True) if hasattr(option, "model_dump") else dict(option) for option in options]
        allowed = await self.on_permission({"sessionId": session_id, "toolCall": tool_payload, "options": option_payloads, **kwargs}) if self.on_permission else False
        if allowed:
            allow_option = next((option for option in options if getattr(option, "kind", "") in {"allow_once", "allow_always"}), options[0] if options else None)
            option_id = getattr(allow_option, "option_id", None) or getattr(allow_option, "optionId", None) or "allow"
            return RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", optionId=option_id))
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def read_text_file(self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any) -> ReadTextFileResponse:
        raise RuntimeError("Client-side file reads are disabled; Hermes must use its sandbox tools.")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> WriteTextFileResponse | None:
        raise RuntimeError("Client-side file writes are disabled; Hermes must use its sandbox tools.")

    async def create_terminal(self, command: str, session_id: str, args: list[str] | None = None, cwd: str | None = None, env: list[Any] | None = None, output_byte_limit: int | None = None, **kwargs: Any) -> CreateTerminalResponse:
        raise RuntimeError("Client-side terminal execution is disabled; Hermes must use its sandbox tools.")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        raise RuntimeError("Client-side terminal output is disabled.")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> ReleaseTerminalResponse | None:
        return ReleaseTerminalResponse()

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> WaitForTerminalExitResponse:
        raise RuntimeError("Client-side terminal execution is disabled.")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        return KillTerminalResponse()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"Unsupported ACP client extension method: {method}")

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        logger.debug("Ignoring ACP client extension notification: %s", method)

    def on_connect(self, conn: Any) -> None:
        return None


class HermesACPClient:
    def __init__(
        self,
        command: str = HERMES_ACP_COMMAND,
        args: str = HERMES_ACP_ARGS,
        cwd: str | None = None,
        timeout_seconds: float = HERMES_ACP_TIMEOUT_SECONDS,
        on_event: EventCallback | None = None,
        on_permission: PermissionCallback | None = None,
    ) -> None:
        self.command = command
        self.args = shlex.split(args) if isinstance(args, str) else list(args)
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.on_event = on_event
        self.on_permission = on_permission

    async def __aenter__(self) -> "HermesACPClient":
        self._check_command()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def start(self) -> None:
        self._check_command()

    async def close(self) -> None:
        return None

    def _check_command(self) -> None:
        if not shutil.which(self.command):
            raise RuntimeError(f"Hermes ACP command not found on PATH: {self.command!r}")

    def _sandboxed_command(self) -> tuple[str, list[str]]:
        self._check_command()
        if not LOCAL_SANDBOX_ENFORCE_PROCESS or not self.cwd:
            return self.command, self.args
        bwrap = shutil.which(BWRAP_COMMAND)
        if not bwrap:
            raise RuntimeError(f"Local sandbox process isolation requires {BWRAP_COMMAND!r}")
        sandbox_dir = str(Path(self.cwd).resolve())
        return bwrap, [
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--share-net",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            sandbox_dir,
            sandbox_dir,
            "--chdir",
            sandbox_dir,
            self.command,
            *self.args,
        ]

    async def prompt_once(self, prompt: str) -> tuple[str, dict[str, Any]]:
        command, args = self._sandboxed_command()
        client = _WenSaiACPClient(on_event=self.on_event, on_permission=self.on_permission)
        async with spawn_agent_process(client, command, *args, cwd=self.cwd, use_unstable_protocol=True) as (conn, _process):
            await asyncio.wait_for(
                conn.initialize(
                    PROTOCOL_VERSION,
                    client_capabilities=ClientCapabilities(),
                    client_info=Implementation(name="wensai-agentsdk", version="0.1.0"),
                ),
                timeout=self.timeout_seconds,
            )
            session = await asyncio.wait_for(conn.new_session(cwd=self.cwd or ".", mcp_servers=[]), timeout=self.timeout_seconds)
            response = await asyncio.wait_for(
                conn.prompt([TextContentBlock(type="text", text=prompt)], session_id=session.session_id),
                timeout=self.timeout_seconds,
            )
            metadata = response.model_dump(by_alias=True) if hasattr(response, "model_dump") else {}
            return "".join(client.message_chunks).strip(), metadata

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import shlex
from typing import Any, Awaitable, Callable

from app.config import BWRAP_COMMAND, HERMES_ACP_ARGS, HERMES_ACP_COMMAND, HERMES_ACP_TIMEOUT_SECONDS, LOCAL_SANDBOX_ENFORCE_PROCESS

logger = logging.getLogger(__name__)

PermissionCallback = Callable[[dict[str, Any]], Awaitable[bool]]
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


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
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task | None = None
        self._message_chunks: list[str] = []

    async def __aenter__(self) -> "HermesACPClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def start(self) -> None:
        if self._process:
            return
        command, args = self._sandboxed_command()
        self._process = await asyncio.create_subprocess_exec(
            command,
            *args,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._drain_stderr())

    async def close(self) -> None:
        if not self._process:
            return
        if self._reader_task:
            self._reader_task.cancel()
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None

    def _sandboxed_command(self) -> tuple[str, list[str]]:
        if not LOCAL_SANDBOX_ENFORCE_PROCESS or not self.cwd:
            return self.command, self.args
        bwrap = shutil.which(BWRAP_COMMAND)
        if not bwrap:
            raise RuntimeError(f"Local sandbox process isolation requires {BWRAP_COMMAND!r}")
        sandbox_dir = self.cwd
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
        await self._request("initialize", {"protocolVersion": 1, "clientCapabilities": {}, "clientInfo": {"name": "wensai-agentsdk", "version": "0.1.0"}})
        session = await self._request("session/new", {"cwd": self.cwd or ".", "mcpServers": []})
        session_id = session["sessionId"]
        result = await self._request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]})
        return "".join(self._message_chunks).strip(), result

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await self.start()
        assert self._process and self._process.stdin
        message_id = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        self._process.stdin.write(self._encode({"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}))
        await self._process.stdin.drain()
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        finally:
            self._pending.pop(message_id, None)
        if "error" in response:
            raise RuntimeError(f"ACP {method} failed: {response['error']}")
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    async def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                return
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("Ignoring non-JSON ACP output: %r", line[:500])
                continue
            await self._handle_message(message)

    async def _drain_stderr(self) -> None:
        assert self._process and self._process.stderr
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            logger.debug("hermes acp stderr: %s", line.decode("utf-8", errors="replace").rstrip())

    async def _handle_message(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        if isinstance(message_id, int) and ("result" in message or "error" in message):
            future = self._pending.get(message_id)
            if future and not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "session/update":
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            content = update.get("content") if isinstance(update.get("content"), dict) else {}
            if update.get("sessionUpdate") == "agent_message_chunk" and content.get("type") == "text":
                self._message_chunks.append(str(content.get("text") or ""))
            if self.on_event:
                await self.on_event(method, params)
            return

        if method == "session/request_permission":
            allowed = await self.on_permission(params) if self.on_permission else False
            await self._send_result(
                message_id,
                {"outcome": {"outcome": "selected", "optionId": "allow"}}
                if allowed
                else {"outcome": {"outcome": "cancelled"}},
            )

    async def _send_result(self, message_id: Any, result: dict[str, Any]) -> None:
        assert self._process and self._process.stdin
        self._process.stdin.write(self._encode({"jsonrpc": "2.0", "id": message_id, "result": result}))
        await self._process.stdin.drain()

    @staticmethod
    def _encode(payload: dict[str, Any]) -> bytes:
        return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

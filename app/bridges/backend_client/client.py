from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import BACKEND_BASE_URL, INTERNAL_API_TOKEN
from app.runs.schemas import TaskDTO


class BackendClient:
    def __init__(self, base_url: str = BACKEND_BASE_URL, token: str = INTERNAL_API_TOKEN) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Internal-Token": token}

    async def get_task(self, task_id: int) -> TaskDTO:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/api/internal/tasks/{task_id}", headers=self.headers)
            response.raise_for_status()
            return TaskDTO.model_validate(response.json())

    async def update_status(self, task_id: int, status: str) -> None:
        await self._post(f"/api/internal/tasks/{task_id}/status", {"status": status})

    async def emit_event(
        self,
        task_id: int,
        event_type: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._post(
            f"/api/internal/tasks/{task_id}/events",
            {"type": event_type, "content": content, "metadata": metadata or {}},
        )

    async def complete_task(self, task_id: int, result: Any, metadata: dict[str, Any] | None = None) -> None:
        await self._post(f"/api/internal/tasks/{task_id}/result", {"message": "任务完成", "result": result, "metadata": metadata or {}})

    async def fail_task(self, task_id: int, error: str, metadata: dict[str, Any] | None = None) -> None:
        await self._post(f"/api/internal/tasks/{task_id}/error", {"error": error, "metadata": metadata or {}})

    async def create_approval(self, task_id: int, action: str, risk: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._post(
            f"/api/internal/tasks/{task_id}/approvals",
            {"action_type": action, "risk_level": risk, "description": action, "payload": payload},
        )

    async def get_approval(self, approval_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/api/internal/approvals/{approval_id}", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def upload_file(self, task_id: int, path: Path) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120) as client:
            with path.open("rb") as file_obj:
                response = await client.post(
                    f"{self.base_url}/api/internal/tasks/{task_id}/files",
                    headers=self.headers,
                    files={"file": (path.name, file_obj, "application/octet-stream")},
                )
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

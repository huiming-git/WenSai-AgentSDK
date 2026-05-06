from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AgentRunCreate(BaseModel):
    task_id: int


class AgentRunResponse(BaseModel):
    run_id: str
    task_id: int
    status: str


class TaskDTO(BaseModel):
    id: int
    owner_id: int
    workspace_id: Optional[int] = None
    workspace_root_path: Optional[str] = None
    title: str
    prompt: str
    runtime: str
    agent_type: str = "hermes_acp"
    model: str = "default"
    input: dict[str, Any] | None = None
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RuntimeResult(BaseModel):
    output_text: str
    output_files: list[str] = []
    metadata: dict[str, Any] = {}

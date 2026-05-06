from dataclasses import dataclass
from pathlib import Path

from app.bridges.backend_client.client import BackendClient
from app.runs.schemas import TaskDTO


@dataclass(slots=True)
class AgentContext:
    task: TaskDTO
    workspace_dir: Path
    backend: BackendClient
    profile: dict

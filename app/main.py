import logging
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import INTERNAL_API_TOKEN
from app.runs.runner import TaskRunner
from app.runs.schemas import AgentRunCreate, AgentRunResponse
from app.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

app = FastAPI(title="WenSai AgentSDK", version="0.1.0")
runs: dict[str, dict[str, int | str]] = {}


async def run_agent_task(run_id: str, task_id: int) -> None:
    runs[run_id]["status"] = "running"
    runs[run_id]["status"] = await TaskRunner().run(task_id)


class SandboxCleanupRequest(BaseModel):
    workspace_root_path: str | None = None


class SandboxFileDeleteRequest(BaseModel):
    relative_path: str
    area: str = "input"
    workspace_root_path: str | None = None


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if x_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/internal/agent-runs", response_model=AgentRunResponse, dependencies=[Depends(require_internal_token)])
async def create_agent_run(run: AgentRunCreate, background_tasks: BackgroundTasks):
    # FastAPI background task keeps this service simple for the first cut. It
    # can later be swapped for a queue without changing backend's contract.
    run_id = f"run_{uuid.uuid4().hex}"
    runs[run_id] = {"run_id": run_id, "task_id": run.task_id, "status": "accepted"}
    background_tasks.add_task(run_agent_task, run_id, run.task_id)
    return AgentRunResponse(run_id=run_id, task_id=run.task_id, status="accepted")


@app.get("/internal/agent-runs/{run_id}", dependencies=[Depends(require_internal_token)])
async def get_agent_run(run_id: str):
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@app.post("/internal/agent-runs/{run_id}/cancel", dependencies=[Depends(require_internal_token)])
async def cancel_agent_run(run_id: str):
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run["status"] = "cancelled"
    return run


def _safe_relative_path(value: str | None, fallback: str) -> Path:
    raw = (value or fallback or "upload.bin").replace("\\", "/").strip("/")
    parts = [part for part in Path(raw).parts if part not in {"", ".", ".."}]
    if not parts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return Path(*parts)


@app.post("/internal/tasks/{task_id}/sandbox/files", dependencies=[Depends(require_internal_token)])
async def receive_sandbox_file(
    task_id: int,
    file: UploadFile = File(...),
    relative_path: str | None = Form(default=None),
    workspace_root_path: str | None = Form(default=None),
):
    safe_path = _safe_relative_path(relative_path, file.filename or "upload.bin")

    workspace = WorkspaceManager().task_dir(task_id, workspace_root_path)
    inputs_dir = workspace / "input"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    target = inputs_dir / safe_path
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    await file.close()

    return {"task_id": task_id, "filename": str(safe_path), "path": str(target)}


@app.delete("/internal/tasks/{task_id}/sandbox/files", dependencies=[Depends(require_internal_token)])
async def delete_sandbox_file(task_id: int, request: SandboxFileDeleteRequest):
    safe_path = _safe_relative_path(request.relative_path, request.relative_path)
    workspace = WorkspaceManager().task_dir(task_id, request.workspace_root_path)
    area = request.area.strip().lower()
    if area not in {"input", "output"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sandbox file area")
    area_dir = (workspace / area).resolve()
    target = (area_dir / safe_path).resolve()
    if not str(target).startswith(str(area_dir)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    if target.exists():
        if target.is_dir():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refusing to delete directory through file endpoint")
        target.unlink()

    return {"task_id": task_id, "filename": str(safe_path), "path": str(target), "status": "deleted"}


@app.delete("/internal/tasks/{task_id}/sandbox", dependencies=[Depends(require_internal_token)])
async def cleanup_sandbox(task_id: int, request: SandboxCleanupRequest | None = None):
    WorkspaceManager().cleanup(task_id, request.workspace_root_path if request else None)
    return {"task_id": task_id, "status": "deleted"}

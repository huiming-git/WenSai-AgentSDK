import shutil
from pathlib import Path

from app.config import LOCAL_SANDBOX_DIRNAME, SANDBOX_BACKEND, WORKSPACE_ROOT
from app.runs.schemas import TaskDTO


class WorkspaceManager:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or WORKSPACE_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def prepare(self, task: TaskDTO) -> Path:
        if SANDBOX_BACKEND == "cube":
            raise RuntimeError(
                "SANDBOX_BACKEND=cube requires the official CubeSandbox execution adapter. "
                "Use SANDBOX_BACKEND=local for the directory fallback."
            )
        workspace = self.task_dir(task.id)
        if task.workspace_root_path:
            workspace = self.task_dir(task.id, task.workspace_root_path)
        workspace.mkdir(parents=True, exist_ok=True)
        for name in ("input", "output", "temp", "logs"):
            (workspace / name).mkdir(parents=True, exist_ok=True)
        (workspace / ".wensai-task.md").write_text(
            "\n".join(
                [
                    f"# {task.title}",
                    "",
                    f"Runtime: {task.runtime}",
                    f"Local sandbox: {workspace}",
                    "",
                    "Agent boundary: read and write task artifacts inside this local sandbox only. Inputs are under input/ and outputs belong under output/.",
                    "",
                    task.prompt,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return workspace

    def task_dir(self, task_id: int, workspace_root_path: str | None = None) -> Path:
        return self.cube_root(workspace_root_path) / f"sandbox-{task_id}"

    def cube_root(self, workspace_root_path: str | None = None) -> Path:
        base = Path(workspace_root_path).expanduser().resolve() if workspace_root_path else self.root
        return base / LOCAL_SANDBOX_DIRNAME

    def cleanup(self, task_id: int, workspace_root_path: str | None = None) -> None:
        shutil.rmtree(self.task_dir(task_id, workspace_root_path), ignore_errors=True)
        shutil.rmtree(self.legacy_cube_task_dir(task_id, workspace_root_path), ignore_errors=True)
        shutil.rmtree(self.legacy_task_dir(task_id, workspace_root_path), ignore_errors=True)

    def legacy_cube_task_dir(self, task_id: int, workspace_root_path: str | None = None) -> Path:
        base = Path(workspace_root_path).expanduser().resolve() if workspace_root_path else self.root
        return base / "CubeSandbox" / f"sandbox-{task_id}"

    def legacy_task_dir(self, task_id: int, workspace_root_path: str | None = None) -> Path:
        base = Path(workspace_root_path).expanduser().resolve() if workspace_root_path else self.root
        return base / f"task-{task_id}"

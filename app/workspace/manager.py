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
        parent_task_id = self.parent_task_id(task)
        if parent_task_id and parent_task_id != task.id:
            self.inherit_parent_inputs(parent_task_id, workspace, task.workspace_root_path)
        self.write_conversation_context(task, workspace)
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

    def parent_task_id(self, task: TaskDTO) -> int | None:
        value = (task.input or {}).get("parent_task_id") if isinstance(task.input, dict) else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def inherit_parent_inputs(self, parent_task_id: int, workspace: Path, workspace_root_path: str | None = None) -> None:
        parent_workspace = self.task_dir(parent_task_id, workspace_root_path)
        parent_input = parent_workspace / "input"
        if not parent_input.exists():
            return
        shutil.copytree(parent_input, workspace / "input", dirs_exist_ok=True)

    def write_conversation_context(self, task: TaskDTO, workspace: Path) -> None:
        context = (task.input or {}).get("conversation_context") if isinstance(task.input, dict) else None
        if not isinstance(context, str) or not context.strip():
            return
        (workspace / "input" / "conversation_context.md").write_text(context.strip() + "\n", encoding="utf-8")

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

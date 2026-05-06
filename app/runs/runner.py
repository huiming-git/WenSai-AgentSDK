import logging

from app.bridges.backend_client.client import BackendClient
from app.outputs.collector import OutputCollector
from app.profiles.manager import ProfileManager
from app.runtimes import RuntimeFactory
from app.runs.context import AgentContext
from app.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


class TaskRunner:
    def __init__(
        self,
        backend: BackendClient | None = None,
        workspace_manager: WorkspaceManager | None = None,
        runtime_factory: RuntimeFactory | None = None,
        profile_manager: ProfileManager | None = None,
    ) -> None:
        self.backend = backend or BackendClient()
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.runtime_factory = runtime_factory or RuntimeFactory()
        self.profile_manager = profile_manager or ProfileManager()

    async def run(self, task_id: int) -> None:
        try:
            task = await self.backend.get_task(task_id)
            await self.backend.update_status(task_id, "running")

            workspace_dir = self.workspace_manager.prepare(task)
            profile = self.profile_manager.resolve(task)
            context = AgentContext(task=task, workspace_dir=workspace_dir, backend=self.backend, profile=profile)

            runtime = self.runtime_factory.create(task.agent_type or task.runtime)
            result = await runtime.run(context)

            archived = await OutputCollector(context).archive_outputs()
            await self.backend.emit_event(task_id, "file_saved", "输出文件已归档", {"files": archived})
            await self.backend.complete_task(task_id, {"message": result.output_text, "files": archived, "metadata": result.metadata}, result.metadata)
        except Exception as exc:
            logger.exception("Task run failed: task_id=%s", task_id)
            await self.backend.fail_task(task_id, str(exc))

from pathlib import Path

from app.runs.context import AgentContext


class OutputCollector:
    def __init__(self, context: AgentContext) -> None:
        self.context = context

    async def archive_outputs(self) -> list[dict]:
        outputs_dir = self.context.workspace_dir / "output"
        if not outputs_dir.exists():
            return []

        archived = []
        for path in outputs_dir.rglob("*"):
            if path.is_file():
                archived.append(await self.context.backend.upload_file(self.context.task.id, path))
        return archived

from app.runs.schemas import TaskDTO


class ProfileManager:
    def resolve(self, task: TaskDTO) -> dict:
        return {
            "runtime": task.runtime,
            "max_autonomy": True,
            "approval_policy": "backend",
        }

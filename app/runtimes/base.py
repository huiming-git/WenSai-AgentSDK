from abc import ABC, abstractmethod

from app.runs.context import AgentContext
from app.runs.schemas import RuntimeResult


class AgentRuntime(ABC):
    @abstractmethod
    async def run(self, context: AgentContext) -> RuntimeResult:
        """Execute a task and return the final runtime result."""

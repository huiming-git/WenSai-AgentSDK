from app.runtimes.base import AgentRuntime
from app.runtimes.hermes_acp.runtime import HermesACPRuntime


class RuntimeFactory:
    def create(self, runtime_name: str) -> AgentRuntime:
        normalized = runtime_name.strip().lower()
        if normalized in {"hermes", "hermes-acp", "hermes_acp"}:
            return HermesACPRuntime()
        raise ValueError(f"Unsupported AgentRuntime: {runtime_name}")

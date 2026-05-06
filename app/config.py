import os

from dotenv import load_dotenv

load_dotenv()


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "dev-internal-token")

AGENTSDK_HOST = os.getenv("AGENTSDK_HOST", "0.0.0.0")
AGENTSDK_PORT = int(os.getenv("AGENTSDK_PORT", "8010"))

WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "./workspaces")
SANDBOX_BACKEND = os.getenv("SANDBOX_BACKEND", "local").strip().lower()
LOCAL_SANDBOX_DIRNAME = os.getenv("LOCAL_SANDBOX_DIRNAME", os.getenv("CUBESANDBOX_DIRNAME", "local-sandbox"))
LOCAL_SANDBOX_ENFORCE_PROCESS = os.getenv(
    "LOCAL_SANDBOX_ENFORCE_PROCESS",
    os.getenv("CUBESANDBOX_ENFORCE_PROCESS", "true"),
).strip().lower() in {"1", "true", "yes", "on"}
BWRAP_COMMAND = os.getenv("BWRAP_COMMAND", "bwrap")

# Official CubeSandbox is a host-level MicroVM service. AgentSDK should call it
# over its E2B-compatible API instead of running Cube components in this container.
CUBE_API_URL = os.getenv("CUBE_API_URL", "")
CUBE_API_KEY = os.getenv("CUBE_API_KEY", "dummy")
CUBE_TEMPLATE_ID = os.getenv("CUBE_TEMPLATE_ID", "")
DEFAULT_RUNTIME = os.getenv("DEFAULT_RUNTIME", "hermes-acp")

HERMES_ACP_COMMAND = os.getenv("HERMES_ACP_COMMAND", "hermes")
HERMES_ACP_ARGS = os.getenv("HERMES_ACP_ARGS", "acp")
HERMES_ACP_TIMEOUT_SECONDS = float(os.getenv("HERMES_ACP_TIMEOUT_SECONDS", "900"))
APPROVAL_POLL_SECONDS = float(os.getenv("APPROVAL_POLL_SECONDS", "2"))
APPROVAL_TIMEOUT_SECONDS = float(os.getenv("APPROVAL_TIMEOUT_SECONDS", "3600"))

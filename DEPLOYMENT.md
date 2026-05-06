# WenSai AgentSDK 部署文档

AgentSDK 是 Agent 执行服务，只接收 Backend 派发的 `task_id`，读取任务详情，运行 Runtime，并通过 Backend internal API 回写状态、事件、审批、结果、错误和文件。

Frontend 不能访问 AgentSDK。Backend 也不直接启动 Hermes。

生产版如果使用官方 CubeSandbox，CubeSandbox 本体必须部署在宿主机 / 裸机层，AgentSDK 只通过 E2B 兼容 API 调用它。不要把 CubeMaster、Cubelet、CubeShim、network-agent 放进 AgentSDK 容器。

## 环境变量

复制并修改：

```bash
cp .env.example .env
```

生产推荐：

```ini
BACKEND_BASE_URL=http://backend:8000
INTERNAL_API_TOKEN=必须和 Backend 一致
AGENTSDK_HOST=0.0.0.0
AGENTSDK_PORT=8010
WORKSPACE_ROOT=/data/agent-workspaces
SANDBOX_BACKEND=cube
CUBE_API_URL=http://host.docker.internal:3000
CUBE_API_KEY=dummy
CUBE_TEMPLATE_ID=你的 Cube 模板 ID
DEFAULT_RUNTIME=hermes-acp
HERMES_ACP_COMMAND=hermes
HERMES_ACP_ARGS=acp
HERMES_ACP_TIMEOUT_SECONDS=900
APPROVAL_POLL_SECONDS=2
APPROVAL_TIMEOUT_SECONDS=3600
```

本地 fallback：

```ini
SANDBOX_BACKEND=local
LOCAL_SANDBOX_DIRNAME=local-sandbox
LOCAL_SANDBOX_ENFORCE_PROCESS=true
BWRAP_COMMAND=bwrap
```

`local-sandbox` 只是目录级本地沙盒，不等同于官方 CubeSandbox MicroVM。

## Dockerfile

当前仓库已提供 `Dockerfile`。它只构建 AgentSDK 服务，不安装官方 CubeSandbox 宿主机组件。

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/agent-workspaces /data/agent-profiles

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

Hermes 安装方式取决于实际发行方式。关键是容器里执行 `hermes acp` 必须可用。

## Compose 服务片段

```yaml
services:
  agentsdk:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      BACKEND_BASE_URL: http://backend:8000
      INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN}
      AGENTSDK_HOST: 0.0.0.0
      AGENTSDK_PORT: 8010
      WORKSPACE_ROOT: /data/agent-workspaces
      SANDBOX_BACKEND: cube
      CUBE_API_URL: http://host.docker.internal:3000
      CUBE_API_KEY: dummy
      CUBE_TEMPLATE_ID: ${CUBE_TEMPLATE_ID}
    expose:
      - "8010"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - agent_workspaces:/data/agent-workspaces
      - agent_profiles:/data/agent-profiles
```

不要使用 `ports` 暴露到公网。只允许 Docker 内网中的 Backend 访问。

## 工作目录

本地 fallback 每个任务使用独立工作区：

```text
/data/agent-workspaces/local-sandbox/sandbox-{task_id}/input
/data/agent-workspaces/local-sandbox/sandbox-{task_id}/output
/data/agent-workspaces/local-sandbox/sandbox-{task_id}/temp
/data/agent-workspaces/local-sandbox/sandbox-{task_id}/logs
```

长期 profile 建议：

```text
/data/agent-profiles/hermes/user_{user_id}/workspace_{workspace_id}/
```

## Internal API

Backend 调 AgentSDK：

- `POST /internal/agent-runs`
- `GET /internal/agent-runs/{run_id}`
- `POST /internal/agent-runs/{run_id}/cancel`
- `POST /internal/tasks/{task_id}/sandbox/files`

所有请求必须带：

```http
X-Internal-Token: <INTERNAL_API_TOKEN>
```

## Runtime

当前支持：

- `hermes_acp` / `hermes-acp`：Hermes ACP Runtime。

Hermes ACP 原始事件必须通过 `ACPEventMapper` 转成统一 `task_events`，不能让前端依赖 Hermes 原始结构。

## 本地运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

## 安全要求

- AgentSDK 不暴露公网。
- 官方 CubeSandbox 不运行在 AgentSDK 容器内。
- 只挂载 `/data/agent-workspaces` 和 `/data/agent-profiles` 等必要目录。
- 高风险工具调用必须通过 Backend approval。
- 不要把 JWT、用户密钥、internal token 注入 Agent prompt。
- Hermes 执行 shell/browser 时，应限制容器权限、网络和挂载。

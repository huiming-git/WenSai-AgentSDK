# WenSai AgentSDK

WenSai AgentSDK 是问赛的 Agent 执行桥接服务。它接收 Backend 派发的 `task_id`，再从 Backend internal API 读取任务详情，运行 runtime，最后把状态、事件、审批、结果和文件回写给 Backend。

AgentSDK 不对公网开放。Frontend 永远不应该直接访问 AgentSDK。

## 系统位置

```text
Backend
  -> AgentSDK /internal/*

AgentSDK
  -> Backend /api/internal/*
  -> Hermes ACP runtime in local fallback
  -> official CubeSandbox API in production target
```

## 职责

- 接收 Backend task dispatch。
- 拉取任务详情。
- 准备任务沙盒。
- 选择 runtime。
- 运行 Hermes ACP。
- 把 ACP/runtime 事件映射成 Backend task events。
- 将高风险权限请求桥接成 Backend approval。
- 收集 output 文件并上传 Backend。
- 删除沙盒内真实文件。

## 当前沙盒后端

AgentSDK 有两个沙盒方向：

| 后端 | 配置 | 状态 |
| --- | --- | --- |
| local fallback | `SANDBOX_BACKEND=local` | 当前可用。使用 `local-sandbox/sandbox-{task_id}` 目录和可选 `bwrap` 进程限制 |
| official CubeSandbox | `SANDBOX_BACKEND=cube` | 生产目标。官方 CubeSandbox 本体运行在宿主机 / 裸机层，AgentSDK 通过 E2B 兼容 API 调用；执行适配层仍需接入 |

注意：`local-sandbox` 不等同于官方 CubeSandbox MicroVM。不要把本地目录命名成 `CubeSandbox`。

## 本地开发

前置条件：

- Python 3.12
- Backend 运行在 `http://127.0.0.1:8000`
- 本机安装 `hermes`，并可执行 `hermes acp`
- 如果启用进程限制，需要安装 `bubblewrap`

安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

本地 `.env` 推荐：

```ini
BACKEND_BASE_URL=http://127.0.0.1:8000
INTERNAL_API_TOKEN=dev-internal-token
AGENTSDK_HOST=0.0.0.0
AGENTSDK_PORT=8010
WORKSPACE_ROOT=./workspaces

SANDBOX_BACKEND=local
LOCAL_SANDBOX_DIRNAME=local-sandbox
LOCAL_SANDBOX_ENFORCE_PROCESS=true
BWRAP_COMMAND=bwrap

DEFAULT_RUNTIME=hermes-acp
HERMES_ACP_COMMAND=hermes
HERMES_ACP_ARGS=acp
```

启动：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

健康检查：

```bash
curl http://127.0.0.1:8010/health
```

## 任务执行流程

```text
Backend POST /internal/agent-runs { task_id }
  -> AgentSDK accepts run
  -> TaskRunner.get_task(task_id)
  -> WorkspaceManager.prepare(task)
  -> RuntimeFactory.create(task.agent_type or task.runtime)
  -> HermesACPRuntime.run(context)
  -> EventEmitter emits normalized events to Backend
  -> ApprovalBridge waits for user decisions through Backend
  -> OutputCollector archives output files to Backend
  -> Backend marks task completed/failed
```

## Internal API

Backend 调 AgentSDK：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/internal/agent-runs` | 接收 task dispatch |
| `GET` | `/internal/agent-runs/{run_id}` | 查询 run |
| `POST` | `/internal/agent-runs/{run_id}/cancel` | 标记取消 |
| `POST` | `/internal/tasks/{task_id}/sandbox/files` | 写入 sandbox input 文件 |
| `DELETE` | `/internal/tasks/{task_id}/sandbox/files` | 删除 sandbox input/output 文件 |
| `DELETE` | `/internal/tasks/{task_id}/sandbox` | 删除整个任务 sandbox |

所有接口必须带：

```http
X-Internal-Token: <INTERNAL_API_TOKEN>
```

AgentSDK 回写 Backend：

- `GET /api/internal/tasks/{task_id}`
- `POST /api/internal/tasks/{task_id}/status`
- `POST /api/internal/tasks/{task_id}/events`
- `POST /api/internal/tasks/{task_id}/result`
- `POST /api/internal/tasks/{task_id}/error`
- `POST /api/internal/tasks/{task_id}/approvals`
- `GET /api/internal/approvals/{approval_id}`
- `GET /api/internal/approvals/{approval_id}/wait`
- `POST /api/internal/tasks/{task_id}/files`

## 目录结构

```text
app/
  main.py                         Internal API entry
  config.py                       环境变量
  runs/
    schemas.py                    DTO 和 RuntimeResult
    context.py                    AgentContext
    runner.py                     TaskRunner 编排
  workspace/
    manager.py                    local-sandbox 准备、文件目录、清理
  runtimes/
    base.py                       AgentRuntime 抽象
    factory.py                    runtime 选择
    hermes_acp/
      client.py                   ACP JSON-RPC client
      event_mapper.py             ACP event -> Backend event
      runtime.py                  Hermes runtime
    tools/router.py               工具风险分级
  bridges/
    backend_client/client.py      Backend internal API client
    event_bridge/emitter.py       事件回写
    approval_bridge/bridge.py     权限审批桥
  outputs/collector.py            output 文件归档
  profiles/manager.py             profile 解析入口
tests/
  test_agentsdk.py
```

## 文件布局

local fallback 每个任务目录：

```text
WORKSPACE_ROOT/
  local-sandbox/
    sandbox-{task_id}/
      .wensai-task.md
      input/
      output/
      temp/
      logs/
```

Agent 输入文件写入 `input/`，最终产物应写入 `output/`。`OutputCollector` 只归档 `output/`。

## Docker

本工程提供 [Dockerfile](./Dockerfile)。它构建 AgentSDK 服务，不安装官方 CubeSandbox 宿主机组件。

```bash
docker build -t wensai-agentsdk:latest .
```

生产推荐使用仓库根目录 [docker-compose.prod.yml](../docker-compose.prod.yml)。官方 CubeSandbox 应安装在宿主机 / 裸机层。

## 测试

```bash
pytest
```

当前测试覆盖：

- runtime factory
- ACP event mapper
- internal token
- sandbox 文件上传
- sandbox 文件删除
- sandbox cleanup
- legacy `CubeSandbox` 目录清理兼容

## 生产注意

- AgentSDK 不暴露公网，只允许 Backend 访问。
- `INTERNAL_API_TOKEN` 必须和 Backend 一致。
- `SANDBOX_BACKEND=cube` 是生产目标配置；启用前必须完成官方 CubeSandbox E2B API 执行适配层。
- 官方 CubeSandbox 运行在宿主机，不运行在 AgentSDK 容器。
- local fallback 可以用于开发，但隔离级别不是 MicroVM。

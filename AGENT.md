# WenSai AgentSDK Agent Guide

本文面向维护 AgentSDK 的代码 Agent。AgentSDK 是执行层桥接服务，安全边界比普通后端代码更严格。

## 职责边界

AgentSDK 负责：

- 接收 Backend 派发的 `task_id`。
- 通过 Backend internal API 拉任务详情。
- 准备沙盒。
- 运行 runtime。
- 映射 runtime events。
- 将权限请求桥接到 Backend approval。
- 上传 output 文件。
- 删除 sandbox 内真实文件。

AgentSDK 不负责：

- 给 Frontend 提供 API。
- 管理用户登录、JWT 或工作区权限。
- 直接写 Backend 数据库。
- 暴露公网端口。
- 在容器内运行官方 CubeSandbox 宿主机组件。

## 关键边界

```text
Backend -> AgentSDK internal endpoints
AgentSDK -> Backend /api/internal endpoints
AgentSDK -> sandbox/runtime
```

所有 AgentSDK endpoint 都必须校验 `X-Internal-Token`。

## 重要文件

| 路径 | 说明 |
| --- | --- |
| `app/main.py` | Internal API、文件写入/删除、run 接收 |
| `app/config.py` | 环境变量和 sandbox backend 配置 |
| `app/runs/runner.py` | TaskRunner 主编排 |
| `app/runs/context.py` | AgentContext |
| `app/workspace/manager.py` | local-sandbox 目录准备和清理 |
| `app/runtimes/factory.py` | runtime 选择 |
| `app/runtimes/hermes_acp/client.py` | Hermes ACP JSON-RPC client 和 bwrap wrapper |
| `app/runtimes/hermes_acp/runtime.py` | Hermes runtime 编排 |
| `app/runtimes/hermes_acp/event_mapper.py` | ACP update 映射 |
| `app/runtimes/tools/router.py` | 工具风险分级 |
| `app/bridges/backend_client/client.py` | Backend internal API client |
| `app/bridges/approval_bridge/bridge.py` | approval 等待 |
| `app/bridges/event_bridge/emitter.py` | 事件发送 |
| `app/outputs/collector.py` | output 文件归档 |
| `tests/test_agentsdk.py` | 当前测试 |

## 沙盒后端规则

### local fallback

配置：

```ini
SANDBOX_BACKEND=local
LOCAL_SANDBOX_DIRNAME=local-sandbox
LOCAL_SANDBOX_ENFORCE_PROCESS=true
BWRAP_COMMAND=bwrap
```

目录：

```text
WORKSPACE_ROOT/local-sandbox/sandbox-{task_id}/
```

规则：

- 输入文件只写 `input/`。
- Agent 产物写 `output/`。
- 删除文件 endpoint 只允许删除 `input` 或 `output` 下的文件。
- 路径必须经过 `_safe_relative_path`，禁止 `..` 和绝对路径。
- legacy `CubeSandbox/sandbox-{task_id}` 只用于清理旧数据兼容，不要再写入。

### official CubeSandbox

配置：

```ini
SANDBOX_BACKEND=cube
CUBE_API_URL=http://host.docker.internal:3000
CUBE_API_KEY=dummy
CUBE_TEMPLATE_ID=<template>
```

规则：

- 官方 CubeSandbox 本体运行在宿主机 / 裸机层。
- AgentSDK 只作为 API caller。
- 不要把 CubeMaster、Cubelet、CubeShim、network-agent 装进 AgentSDK 容器。
- 当前 `cube` 执行适配层仍需接官方 E2B API；未完成前不得把生产任务误导到 local fallback。

## Runtime 规则

- `RuntimeFactory` 负责 runtime name 归一。
- 当前支持 `hermes`, `hermes-acp`, `hermes_acp`。
- Hermes ACP client 使用 line-based JSON-RPC。
- ACP 原始事件不能直接透传给 Frontend；必须通过 `ACPEventMapper` 映射。
- 权限请求必须经过 `ToolRouter` 风险分级和 `ApprovalBridge`。
- 默认不要自动 allow 高风险权限。

## 事件规则

通过 `EventEmitter` 回写 Backend：

```text
agent_runtime_started
agent_message
tool_call_started
tool_call_finished
file_created
agent_runtime_stopped
file_saved
```

新增事件时要同步：

- Backend event schema/response 是否允许。
- Frontend `AgentTaskConversation` 是否能显示。
- 测试是否覆盖。

## 文件规则

上传到 sandbox：

```text
POST /internal/tasks/{task_id}/sandbox/files
```

删除 sandbox 文件：

```text
DELETE /internal/tasks/{task_id}/sandbox/files
```

清理任务 sandbox：

```text
DELETE /internal/tasks/{task_id}/sandbox
```

归档 output：

```text
OutputCollector -> Backend /api/internal/tasks/{task_id}/files
```

不要归档 `input/`、`temp/` 或 `logs/`。

## 错误处理

`TaskRunner.run` 捕获异常后必须调用：

```text
BackendClient.fail_task(task_id, str(exc))
```

不要吞掉异常导致 Backend 永久停留在 `running` 或 `queued`。

## 本地运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

## 验证

```bash
pytest
```

涉及 Hermes ACP 时，应手动确认：

```bash
hermes acp
```

涉及 `bwrap` 时，应确认：

```bash
bwrap --version
```

涉及 Dockerfile 时，在有 Docker 的环境执行：

```bash
docker build -t wensai-agentsdk:local .
```

## 安全要求

- AgentSDK 不开放公网 `ports`。
- Internal token 只用于 Backend 和 AgentSDK。
- 不要把 JWT、LLM key、internal token 写入 prompt。
- 不要在 logs 中输出完整文件内容或密钥。
- 不要默认批准 runtime permission。
- 不要让路径逃出当前 sandbox。

## 禁止事项

- 不要恢复 `fake runtime`、mock runtime 或伪成功路径。
- 不要把官方 CubeSandbox 本体安装到 AgentSDK 容器。
- 不要把 `local-sandbox` 命名成 `CubeSandbox`。
- 不要让 Frontend 访问 AgentSDK。
- 不要只删除内存状态而不删除真实文件。

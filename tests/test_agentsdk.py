from app.runtimes.hermes_acp.event_mapper import ACPEventMapper
from app.runtimes import HermesACPRuntime, RuntimeFactory
from app.config import INTERNAL_API_TOKEN
from app.main import app
from fastapi.testclient import TestClient


def test_runtime_factory_resolves_hermes_acp():
    runtime = RuntimeFactory().create("hermes-acp")
    assert isinstance(runtime, HermesACPRuntime)


def test_acp_event_mapper_maps_agent_message():
    event_type, message, payload = ACPEventMapper().map_update(
        {
            "sessionId": "s1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hello"},
            },
        }
    )
    assert event_type == "agent_message"
    assert message == "hello"
    assert payload["source"] == "hermes_acp"
    assert payload["raw_event"]["sessionUpdate"] == "agent_message_chunk"


def test_internal_sandbox_file_upload_writes_to_task_input(tmp_path, monkeypatch):
    monkeypatch.setattr("app.workspace.manager.WORKSPACE_ROOT", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/internal/tasks/7/sandbox/files",
        files={"file": ("../input.txt", b"hello", "text/plain")},
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "input.txt"
    assert (tmp_path / "local-sandbox" / "sandbox-7" / "input" / "input.txt").read_bytes() == b"hello"


def test_internal_sandbox_cleanup_deletes_task_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.workspace.manager.WORKSPACE_ROOT", str(tmp_path))
    task_dir = tmp_path / "local-sandbox" / "sandbox-8" / "output"
    task_dir.mkdir(parents=True)
    (task_dir / "result.txt").write_text("done", encoding="utf-8")
    legacy_task_dir = tmp_path / "task-8" / "output"
    legacy_task_dir.mkdir(parents=True)
    (legacy_task_dir / "legacy.txt").write_text("legacy", encoding="utf-8")
    client = TestClient(app)

    response = client.delete(
        "/internal/tasks/8/sandbox",
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    )

    assert response.status_code == 200
    assert not (tmp_path / "local-sandbox" / "sandbox-8").exists()
    assert not (tmp_path / "task-8").exists()


def test_internal_sandbox_cleanup_supports_workspace_root_path(tmp_path):
    workspace_root = tmp_path / "local-space"
    task_dir = workspace_root / "local-sandbox" / "sandbox-9" / "output"
    task_dir.mkdir(parents=True)
    (task_dir / "result.txt").write_text("done", encoding="utf-8")
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/internal/tasks/9/sandbox",
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
        json={"workspace_root_path": str(workspace_root)},
    )

    assert response.status_code == 200
    assert not (workspace_root / "local-sandbox" / "sandbox-9").exists()


def test_internal_sandbox_file_upload_supports_workspace_root_path(tmp_path):
    workspace_root = tmp_path / "local-space"
    client = TestClient(app)

    response = client.post(
        "/internal/tasks/10/sandbox/files",
        data={"workspace_root_path": str(workspace_root), "relative_path": "docs/input.txt"},
        files={"file": ("input.txt", b"hello", "text/plain")},
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "docs/input.txt"
    assert (workspace_root / "local-sandbox" / "sandbox-10" / "input" / "docs" / "input.txt").read_bytes() == b"hello"


def test_internal_sandbox_file_delete_removes_real_input_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.workspace.manager.WORKSPACE_ROOT", str(tmp_path))
    target = tmp_path / "local-sandbox" / "sandbox-11" / "input" / "docs" / "input.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/internal/tasks/11/sandbox/files",
        json={"relative_path": "docs/input.txt"},
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "docs/input.txt"
    assert not target.exists()


def test_internal_sandbox_file_delete_supports_output_area(tmp_path, monkeypatch):
    monkeypatch.setattr("app.workspace.manager.WORKSPACE_ROOT", str(tmp_path))
    target = tmp_path / "local-sandbox" / "sandbox-12" / "output" / "result.md"
    target.parent.mkdir(parents=True)
    target.write_text("done", encoding="utf-8")
    client = TestClient(app)

    response = client.request(
        "DELETE",
        "/internal/tasks/12/sandbox/files",
        json={"relative_path": "result.md", "area": "output"},
        headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    )

    assert response.status_code == 200
    assert not target.exists()

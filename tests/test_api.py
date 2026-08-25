import time
from pathlib import Path

from fastapi.testclient import TestClient

from aps_server.config import Settings
from aps_server.main import create_app


def make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / "02_Projects").mkdir(parents=True)
    (vault / "05_ProjectContexts" / "sample" / ".brief").mkdir(parents=True)
    (vault / "scripts").mkdir()
    (vault / "scripts" / "daily_briefing.py").write_text("# test", encoding="utf-8")
    (vault / "02_Projects" / "sample.md").write_text(
        "---\ntype: project\nstatus: In_Progress\nbriefing_id: sample\n---\n# Sample",
        encoding="utf-8",
    )
    (vault / "05_ProjectContexts" / "sample" / ".brief" / "brief.md").write_text(
        "# Brief", encoding="utf-8"
    )
    return vault


def test_auth_and_audit_job(tmp_path):
    settings = Settings(
        vault_path=make_vault(tmp_path),
        data_path=tmp_path / "data",
        operator_token="operator-secret",
        viewer_token="viewer-secret",
        scheduler_token="scheduler-secret",
        sync_before_job=False,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/operations").status_code == 401
        response = client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer operator-secret", "Idempotency-Key": "audit-test-key"},
            json={"operation": "vault.audit", "input": {}, "context": {}},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        for _ in range(100):
            job = client.get(
                f"/v1/jobs/{job_id}", headers={"Authorization": "Bearer operator-secret"}
            ).json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "succeeded"
        assert job["result"] == {"active_projects": 1, "issues": [], "healthy": True}

        duplicate = client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer operator-secret", "Idempotency-Key": "audit-test-key"},
            json={"operation": "vault.audit", "input": {}, "context": {}},
        )
        assert duplicate.json()["job_id"] == job_id


def test_viewer_cannot_run_agent_query(tmp_path):
    settings = Settings(
        vault_path=make_vault(tmp_path),
        data_path=tmp_path / "data",
        operator_token="operator-secret",
        viewer_token="viewer-secret",
        sync_before_job=False,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer viewer-secret"},
            json={
                "operation": "agent.query",
                "input": {"question": "오늘 할 일?"},
                "context": {"project_ids": ["sample"]},
            },
        )
        assert response.status_code == 403

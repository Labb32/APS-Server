import json
import hashlib
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from aps_server.config import Settings
from aps_server.main import create_app


EXAMPLES = json.loads(
    (Path(__file__).parents[1] / "specs" / "content-api.examples.json").read_text(encoding="utf-8")
)


def make_settings(tmp_path: Path) -> Settings:
    vault = tmp_path / "vault"
    vault.mkdir()
    return Settings(
        vault_path=vault,
        data_path=tmp_path / "data",
        operator_token="owner-device-token",
        viewer_token="reader-device-token",
        scheduler_token="scheduler-token",
        sync_before_job=False,
    )


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def auth(token: str = "reader-device-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_content(data_path: Path) -> None:
    content = data_path / "content"
    write_json(content / "daily_briefing.json", EXAMPLES["daily_briefing_response"])
    write_json(content / "project_catalog.json", EXAMPLES["project_catalog_response"])
    write_json(content / "projects" / "aps-server-briefing.json", EXAMPLES["project_briefing_response"])
    write_json(content / "service_maintenance.json", EXAMPLES["service_maintenance_response"])
    write_json(content / "ideas.json", EXAMPLES["ideas_response"])


def test_content_endpoints_return_pre_generated_json(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings)) as client:
        daily = client.get("/v1/content/briefing/daily?format=json", headers=auth())
        assert daily.status_code == 200
        assert daily.json()["content_type"] == "daily_briefing"

        catalog = client.get("/v1/content/projects", headers=auth()).json()
        assert catalog["data"]["projects"][0]["project_id"] == "aps-server-briefing"

        project = client.get(
            "/v1/content/projects/aps-server-briefing/briefing", headers=auth()
        ).json()
        assert project["content_type"] == "project_briefing"

        ideas = client.get("/v1/content/ideas?status=organized", headers=auth()).json()
        assert [item["status"] for item in ideas["data"]["ideas"]] == ["organized"]


def test_content_api_returns_standalone_html_with_security_headers(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/content/briefing/daily?format=html", headers=auth())
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["content-security-policy"].startswith("default-src 'none'")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["etag"].startswith('"')
        assert "APS Daily Briefing" in response.text
        assert "{{" not in response.text

        invalid = client.get("/v1/content/briefing/daily?format=xml", headers=auth())
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_FORMAT"


def test_all_content_queries_have_html_representation(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings)) as client:
        paths = {
            "/v1/content/briefing/daily?format=html": "daily_briefing",
            "/v1/content/projects?format=html": "project_catalog",
            "/v1/content/projects/aps-server-briefing/briefing?format=html": "project_briefing",
            "/v1/content/services/maintenance?scope=all&format=html": "service_maintenance",
            "/v1/content/ideas?format=html": "ideas",
        }
        for path, content_type in paths.items():
            response = client.get(path, headers=auth())
            assert response.status_code == 200
            assert f'content="{content_type}"' in response.text
            assert "{{" not in response.text


def test_html_renderer_escapes_generated_content(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    payload = deepcopy(EXAMPLES["daily_briefing_response"])
    payload["data"]["projects"][0]["summary"] = '</p><script src="https://evil.invalid/x.js"></script>'
    write_json(settings.data_path / "content" / "daily_briefing.json", payload)
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/content/briefing/daily?format=html", headers=auth())
        assert response.status_code == 200
        assert "<script" not in response.text.lower()
        assert "&lt;script" in response.text


def test_missing_content_uses_contract_error(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/content/briefing/daily", headers=auth())
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "CONTENT_NOT_GENERATED"
        assert error["request_id"].startswith("req_")


def test_service_maintenance_scope_filters_stored_result(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings)) as client:
        due = client.get(
            "/v1/content/services/maintenance?scope=due", headers=auth()
        ).json()
        assert due["data"]["scope"] == "due"
        assert due["data"]["services"] == []

        upcoming = client.get(
            "/v1/content/services/maintenance?scope=upcoming", headers=auth()
        ).json()
        assert upcoming["data"]["services"][0]["due_status"] == "upcoming"
        encoded = json.dumps(upcoming["data"], ensure_ascii=False, separators=(",", ":"))
        assert upcoming["sha256"] == hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_content_permissions_do_not_depend_on_request_source(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings), client=("203.0.113.40", 43100)) as client:
        assert client.get("/v1/content/projects", headers=auth()).status_code == 200
        assert client.get(
            "/v1/content/projects", headers=auth("owner-device-token")
        ).status_code == 200

        denied = client.get("/v1/content/projects", headers=auth("scheduler-token"))
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "OPERATION_FORBIDDEN"

        missing = client.get("/v1/content/projects")
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_owner_can_stage_idea_without_codex_job(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/ideas",
            headers=auth("owner-device-token"),
            json={"content": "음성 브리핑을 추가한다.", "tags": ["voice", "voice"]},
        )
        assert response.status_code == 201
        idea_id = response.json()["idea_id"]
        stored = json.loads(
            (settings.data_path / "staging" / "ideas" / f"{idea_id}.json").read_text(
                encoding="utf-8"
            )
        )
        assert stored["content"] == "음성 브리핑을 추가한다."
        assert stored["tags"] == ["voice"]
        assert not list((settings.data_path / "jobs").glob("*.json"))

        denied = client.post(
            "/v1/ideas",
            headers=auth(),
            json={"content": "reader는 추가할 수 없다."},
        )
        assert denied.status_code == 403


def test_owner_can_create_confirmation_preview_without_codex_job(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/project-requests",
            headers=auth("owner-device-token"),
            json={
                "title": "음성 프로젝트 브리핑",
                "objective": "브리핑을 음성으로 제공한다.",
                "constraints": ["기존 결과를 재사용한다."],
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "confirmation_required"
        assert (settings.data_path / "staging" / "project-requests" / f'{payload["request_id"]}.json').is_file()
        assert not list((settings.data_path / "jobs").glob("*.json"))


def test_content_status_is_derived_from_validated_files(tmp_path):
    settings = make_settings(tmp_path)
    seed_content(settings.data_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/content/status", headers=auth())
        assert response.status_code == 200
        payload = response.json()
        assert payload["vault_commit"] == EXAMPLES["daily_briefing_response"]["vault_commit"]
        assert payload["content"]["daily_briefing"]["formats"] == ["json", "html"]
        assert payload["content"]["daily_briefing"]["status"] == "ready"

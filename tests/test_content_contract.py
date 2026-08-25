import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "specs" / "content-api.openapi.json"
EXAMPLES = ROOT / "specs" / "content-api.examples.json"
TEMPLATES = ROOT / "src" / "aps_server" / "templates"


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def resolve_pointer(document: dict, pointer: str):
    assert pointer.startswith("#/"), f"only local references are allowed: {pointer}"
    value = document
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    return value


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_openapi_contract_has_resolvable_local_references():
    contract = load_contract()
    assert contract["openapi"] == "3.1.0"
    assert "agent.query" not in CONTRACT.read_text(encoding="utf-8")
    for node in walk(contract):
        if "$ref" in node:
            resolve_pointer(contract, node["$ref"])


def test_json_examples_cover_requests_and_responses():
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    assert {
        "daily_briefing_response",
        "project_catalog_response",
        "project_briefing_response",
        "service_maintenance_response",
        "ideas_response",
        "create_idea_request",
        "create_idea_response",
        "create_project_request",
        "project_confirmation_required_response",
        "confirm_project_response",
        "content_status_response",
        "error_response",
    } <= examples.keys()


def test_content_queries_offer_json_and_html():
    paths = load_contract()["paths"]
    content_queries = {
        "/v1/content/briefing/daily",
        "/v1/content/projects",
        "/v1/content/projects/{project_id}/briefing",
        "/v1/content/services/maintenance",
        "/v1/content/ideas",
    }
    for path in content_queries:
        media_types = paths[path]["get"]["responses"]["200"]["content"]
        assert set(media_types) == {"application/json", "text/html"}


def test_mutating_requests_are_json_only():
    paths = load_contract()["paths"]
    for path in ("/v1/ideas", "/v1/project-requests"):
        request_content = paths[path]["post"]["requestBody"]["content"]
        assert set(request_content) == {"application/json"}

    confirm = paths["/v1/project-requests/{request_id}/confirm"]["post"]
    assert "requestBody" not in confirm
    assert set(confirm["responses"]["202"]["content"]) == {"application/json"}


def test_fixed_html_templates_are_local_and_script_free():
    expected = {
        "daily_briefing.html": "daily_briefing",
        "project_catalog.html": "project_catalog",
        "project_briefing.html": "project_briefing",
        "service_maintenance.html": "service_maintenance",
        "ideas.html": "ideas",
    }
    for filename, content_type in expected.items():
        content = (TEMPLATES / filename).read_text(encoding="utf-8")
        assert '<meta name="aps-content-type" content="' + content_type + '">' in content
        assert "{{APS_CONTENT_CSS}}" in content
        assert "{{VAULT_COMMIT}}" in content
        assert "{{SHA256}}" in content
        assert "<script" not in content.lower()
        assert not re.search(r"(?:src|href)\s*=\s*[\"']https?://", content, re.IGNORECASE)


def test_shared_content_css_has_no_remote_assets():
    css = (TEMPLATES / "content.css").read_text(encoding="utf-8")
    assert "@import" not in css.lower()
    assert "url(" not in css.lower()

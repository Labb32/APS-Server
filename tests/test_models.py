import pytest
from pydantic import ValidationError

from aps_server.models import JobContext


def test_context_rejects_vault_paths():
    with pytest.raises(ValidationError):
        JobContext(paths=["05_ProjectContexts/project-bnh/.brief"])


def test_context_accepts_logical_project_ids():
    context = JobContext(project_ids=["project-bnh"])
    assert context.project_ids == ["project-bnh"]

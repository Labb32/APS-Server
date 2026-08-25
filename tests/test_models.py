import pytest
from pydantic import ValidationError

from aps_server.models import JobContext


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "C:/secret", "folder\\secret"])
def test_context_rejects_paths_outside_vault(path):
    with pytest.raises(ValidationError):
        JobContext(paths=[path])


def test_context_accepts_vault_relative_paths():
    context = JobContext(paths=["05_ProjectContexts/project-bnh/.brief"])
    assert context.paths == ["05_ProjectContexts/project-bnh/.brief"]

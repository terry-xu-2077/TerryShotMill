import pytest
from shotmill.application.project_transfer_files import (
    project_transfer_media_paths,
    validate_project_transfer_manifest,
)
from shotmill.errors import ConflictError
from test_project_transfer_validation import graph


def test_manifest_requires_exact_logical_aliases():
    source = graph()
    assert project_transfer_media_paths(source) == {"output.mp4"}
    validate_project_transfer_manifest(source, {"output.mp4"})
    with pytest.raises(ConflictError):
        validate_project_transfer_manifest(source, set())
    with pytest.raises(ConflictError):
        validate_project_transfer_manifest(source, {"output.mp4", "unrelated.bin"})


def test_context_history_file_cannot_be_omitted():
    source = graph()
    source.jobs[0].execution_context = {"media": [{"projectRelativePath": "context/frame.png"}]}
    with pytest.raises(ConflictError):
        validate_project_transfer_manifest(source, {"output.mp4"})
    validate_project_transfer_manifest(source, {"output.mp4", "context/frame.png"})


@pytest.mark.parametrize("path", ["../outside", "C:/private", "//server/share"])
def test_manifest_cannot_legitimize_unsafe_record_paths(path):
    source = graph()
    source.jobs[0].assets_snapshot = [{"projectRelativePath": path}]
    with pytest.raises(ValueError):
        validate_project_transfer_manifest(source, {"output.mp4", path})

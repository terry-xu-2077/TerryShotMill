from io import BytesIO
from unittest.mock import Mock

import pytest
from shotmill.application.file_library import FileLibrary
from shotmill.application.result_file_collector import ResultFileCollector
from shotmill.domain.providers import GeneratedOutput
from shotmill.media.file_storage import FileStorage


def test_missing_collected_file_cannot_publish_references(tmp_path, monkeypatch):
    from shotmill.application import result_file_collector

    monkeypatch.setattr(result_file_collector, "result_with_preview", lambda result, _: result)
    storage = FileStorage(tmp_path)
    collected = ResultFileCollector(FileLibrary(storage)).collect(
        "p", "t", "j", GeneratedOutput("clip.mp4", b"video", "video/mp4"),
    )
    storage.resolve(collected.files[0][0]).unlink()
    uow = Mock()
    with pytest.raises(OSError):
        collected.register_files(uow)
    uow.files.register.assert_not_called()
    uow.files.bind.assert_not_called()


def test_identical_outputs_keep_distinct_results_but_share_physical_bytes(tmp_path, monkeypatch):
    from shotmill.application import result_file_collector

    monkeypatch.setattr(result_file_collector, "result_with_preview", lambda result, _: result)
    storage = FileStorage(tmp_path)
    collector = ResultFileCollector(FileLibrary(storage))
    output = GeneratedOutput("clip.mp4", b"same-video", "video/mp4")
    first = collector.collect("p", "t", "job-one", output)
    second = collector.collect("other", "t2", "job-two", output)
    assert first.result.id != second.result.id
    assert first.result.job_id != second.result.job_id
    assert first.files[0][0] == second.files[0][0]
    assert len(list(tmp_path.glob("objects/*/*"))) == 1
    assert first.result.metadata["originalFilename"] == "clip.mp4"
    assert not list((tmp_path / "staging").iterdir())


def test_generated_poster_is_collected_without_project_local_duplicate(tmp_path, monkeypatch):
    from shotmill.application import result_file_collector

    def generate_poster(result, media):
        relative = "thumbnails/poster.png"
        path = media.resolve(result.project_id, relative)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"poster")
        result.preview_url = media.media_url(result.project_id, relative)
        return result

    monkeypatch.setattr(result_file_collector, "result_with_preview", generate_poster)
    storage = FileStorage(tmp_path)
    collected = ResultFileCollector(FileLibrary(storage)).collect(
        "p", "t", "j", GeneratedOutput("clip.mp4", b"video", "video/mp4"),
    )
    assert len(collected.files) == 2
    file, ref = collected.files[1]
    assert ref.slot == "preview" and ref.mime_type == "image/png"
    assert storage.resolve(file).read_bytes() == b"poster"
    assert collected.result.preview_url.endswith(f"{collected.result.id}/preview")
    assert not list((tmp_path / "staging").iterdir())


def test_interrupted_output_does_not_publish_partial_file(tmp_path):
    class Broken(BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("connection lost")
            return super().read(size)

    storage = FileStorage(tmp_path)
    stream = Broken(b"partial")
    with pytest.raises(OSError, match="connection lost"):
        ResultFileCollector(FileLibrary(storage)).collect(
            "p", "t", "j", GeneratedOutput("clip.mp4", stream, "video/mp4"),
        )
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert not stream.closed  # GenerationService owns all response stream lifetimes.

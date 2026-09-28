from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from shotmill.application.project_export_downloads import ProjectExportDownloads
from shotmill.errors import ConflictError, NotFoundError


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    timers = []

    class ControlledTimer:
        def __init__(self, interval, callback, args):
            self.callback, self.args = callback, args
            self.cancelled = False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr("shotmill.application.project_export_downloads.Timer", ControlledTimer)
    cleaned = []

    @contextmanager
    def prepare(project):
        path = tmp_path / f"{project}.zip"
        path.write_bytes(b"complete package")
        try:
            yield path
        finally:
            path.unlink()
            cleaned.append(project)

    service = ProjectExportDownloads(SimpleNamespace(prepare=prepare))
    yield service, timers, cleaned
    service.close()


def test_claim_transfers_cleanup_and_token_is_single_use(downloads):
    service, timers, cleaned = downloads
    token = service.prepare("p")
    path, lifetime = service.claim(token)
    assert path.read_bytes() == b"complete package"
    assert timers[0].cancelled
    with pytest.raises(NotFoundError):
        service.claim(token)
    timers[0].callback(*timers[0].args)  # A timer racing the claim cannot remove the file.
    service.close()
    assert path.exists() and cleaned == []
    lifetime.close()
    assert not path.exists() and cleaned == ["p"]


def test_expiration_cleans_only_its_package_and_releases_capacity(downloads):
    service, timers, cleaned = downloads
    expired = service.prepare("p")
    retained = service.prepare("q")
    with pytest.raises(ConflictError):
        service.prepare("blocked")
    timers[0].callback(*timers[0].args)
    assert cleaned == ["p"]
    with pytest.raises(NotFoundError):
        service.claim(expired)
    service.prepare("replacement")
    path, lifetime = service.claim(retained)
    assert path.exists()
    lifetime.close()


def test_failed_preparation_releases_capacity(downloads):
    service, _, _ = downloads
    original = service.exporter.prepare

    @contextmanager
    def broken(project):
        raise OSError("disk full")
        yield  # pragma: no cover

    service.exporter.prepare = broken
    for _ in range(3):
        with pytest.raises(OSError, match="disk full"):
            service.prepare("failed")
    service.exporter.prepare = original
    assert service.prepare("retry")


def test_shutdown_cleans_pending_and_prevents_new_preparation(downloads):
    service, timers, cleaned = downloads
    token = service.prepare("p")
    service.close()
    assert timers[0].cancelled and cleaned == ["p"]
    with pytest.raises(NotFoundError):
        service.claim(token)
    with pytest.raises(ConflictError):
        service.prepare("q")


def test_shutdown_during_preparation_does_not_publish_or_leak(downloads):
    service, _, cleaned = downloads
    original = service.exporter.prepare

    @contextmanager
    def closing(project):
        with original(project) as path:
            service.close()
            yield path

    service.exporter.prepare = closing
    with pytest.raises(ConflictError):
        service.prepare("p")
    assert cleaned == ["p"]


def test_timer_start_failure_releases_file_and_capacity(downloads, monkeypatch):
    service, _, cleaned = downloads

    def fail_start(self):
        raise RuntimeError("timer unavailable")

    with monkeypatch.context() as patch:
        patch.setattr("shotmill.application.project_export_downloads.Timer.start", fail_start)
        for _ in range(3):
            with pytest.raises(RuntimeError, match="timer unavailable"):
                service.prepare("p")
    assert cleaned == ["p", "p", "p"]
    assert service.prepare("retry")

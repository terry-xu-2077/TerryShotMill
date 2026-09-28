"""Pin owned legacy paths into the global library without rewriting history."""

import mimetypes
from collections.abc import Callable
from pathlib import PurePosixPath

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_transfer_files import project_transfer_media_paths
from shotmill.application.project_transfer_source import read_project_transfer_source
from shotmill.domain.repositories import UnitOfWork
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.legacy_paths import legacy_owner_id


class LegacyFileMigration:
    def __init__(
        self, factory: Callable[[], UnitOfWork], library: FileLibrary, legacy: CleanupStorage,
    ):
        self.factory, self.library, self.legacy = factory, library, legacy

    def migrate_project(self, project_id: str) -> int:
        """Commit all mappings together; never remove sources, snapshots or global bytes.

        Failed copies can leave immutable unregistered objects, not partial visible
        mappings. Retry reuses those bytes. Physical cleanup is a separate gate.
        """
        with self.factory() as uow:
            source = read_project_transfer_source(uow, project_id)
            paths = sorted(path for path in project_transfer_media_paths(source)
                           if not path.startswith("shared/"))
            known_hashes = {asset.project_relative_path: asset.hash for asset in source.assets
                            if asset.hash}
            for relative in paths:
                owner = legacy_owner_id(relative)
                existing = uow.files.get_reference("project", project_id, "legacy_path", owner,
                                                   "content")
                path = self.legacy.resolve(project_id, relative)
                if existing is not None and not path.exists():
                    file = uow.files.get(existing.sha256)
                    if file is None:
                        raise ValueError("Migrated file registration is missing")
                    self.library.storage.verify(file)
                    continue
                self.library.import_path(
                    uow, path, scope_kind="project", scope_id=project_id,
                    owner_kind="legacy_path", owner_id=owner, slot="content",
                    expected_hash=existing.sha256 if existing else known_hashes.get(relative),
                    original_filename=PurePosixPath(relative).name,
                    mime_type=mimetypes.guess_type(relative)[0],
                )
            return len(paths)

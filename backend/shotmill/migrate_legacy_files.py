"""Explicit maintenance entry point; never removes legacy files or upgrades schema."""

import argparse
import json
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.application.legacy_file_migration import LegacyFileMigration
from shotmill.desktop_lock import desktop_data_lock
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.file_storage import FileStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories import SqlAlchemyUnitOfWork


def migrate(data_root: Path, project_ids: list[str]) -> None:
    root = data_root.resolve(strict=True)
    database = root / "shotmill.db"
    if not database.is_file():
        raise ValueError("Existing shotmill.db is required; no empty database will be created")
    with desktop_data_lock(root):
        engine = create_database_engine(f"sqlite+pysqlite:///{database.as_posix()}")
        try:
            sessions = create_session_factory(engine)
            migration = LegacyFileMigration(
                lambda: SqlAlchemyUnitOfWork(sessions), FileLibrary(FileStorage(root / "files")),
                CleanupStorage(root / "projects"),
            )
            for project_id in dict.fromkeys(project_ids):
                count = migration.migrate_project(project_id)
                # Each line reports a committed project; a later failure does not
                # pretend earlier projects rolled back. Re-running is idempotent.
                print(json.dumps({"projectId": project_id, "mappedPaths": count,
                                  "legacyFilesRemoved": 0}), flush=True)
        finally:
            engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--project", action="append", required=True, dest="project_ids")
    parser.add_argument("--apply", action="store_true", required=True,
                        help="Explicitly create mappings; retains every legacy source file")
    args = parser.parse_args()
    migrate(args.data_root, args.project_ids)


if __name__ == "__main__":
    main()

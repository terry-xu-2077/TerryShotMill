import os
import re
from pathlib import Path

from shotmill.media.storage import _resolved_path


class CleanupStorage:
    """Only individually enumerated files under a validated managed project root."""

    def __init__(self, projects_root: Path):
        self.root = _resolved_path(projects_root)

    def resolve(self, project_id: str, relative: str | None = None) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("Invalid project storage identity")
        project = self.root / project_id
        path = project if relative is None else project / relative
        if relative is not None and (
            Path(relative).is_absolute() or ".." in Path(relative).parts or not Path(relative).parts
        ):
            raise ValueError("Invalid managed file path")
        resolved = _resolved_path(path)
        project_root = _resolved_path(project)
        resolved.relative_to(project_root)
        project_root.relative_to(self.root)
        for parent in (path, *path.parents):
            if parent == self.root:
                break
            if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                raise ValueError("Refusing linked storage paths")
        if relative is not None and resolved == project_root:
            raise ValueError("A file path is required")
        return resolved

    def files(self, project_id: str, relative: str | None = None) -> set[str]:
        root = self.resolve(project_id)
        start = self.resolve(project_id, relative) if relative else root
        found = set()
        if start.is_file():
            return {start.relative_to(root).as_posix()}
        if not start.exists():
            return found

        def fail(error: OSError):
            raise error

        for folder, directories, files in os.walk(start, followlinks=False, onerror=fail):
            for name in [*directories, *files]:
                path = Path(folder) / name
                self.resolve(project_id, path.relative_to(root).as_posix())
            found.update((Path(folder) / name).relative_to(root).as_posix() for name in files)
        return found

    def delete_file(self, project_id: str, relative: str) -> None:
        self.resolve(project_id, relative).unlink(missing_ok=True)

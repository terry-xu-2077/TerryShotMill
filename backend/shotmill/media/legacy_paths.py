"""Stable identity for validated legacy logical media paths."""

import hashlib

from shotmill.media.project_package import _portable_path


def legacy_owner_id(relative: str) -> str:
    _portable_path(relative)
    if relative.startswith("shared/"):
        raise ValueError("Shared paths already have logical owners")
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()

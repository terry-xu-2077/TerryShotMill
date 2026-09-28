from __future__ import annotations

import mimetypes

from shotmill.domain.entities import Asset
from shotmill.domain.providers import ResolvedMedia
from shotmill.media.storage import MediaStorage


class MediaResolver:
    def __init__(self, storage: MediaStorage) -> None:
        self.storage = storage

    def resolve(self, asset: Asset, reference: str, role: str | None) -> ResolvedMedia:
        path = self.storage.resolve_read(asset.project_id, asset.project_relative_path)
        if not path.exists():
            raise FileNotFoundError(path)
        mime_type, _ = mimetypes.guess_type(asset.original_filename)
        return ResolvedMedia(
            asset_id=asset.id,
            reference=reference,
            role=role,
            media_type=asset.media_type,
            path=path,
            mime_type=mime_type,
            original_filename=asset.original_filename,
        )

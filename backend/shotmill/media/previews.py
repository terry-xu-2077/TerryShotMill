import logging
from dataclasses import replace

from shotmill.domain.entities import Result
from shotmill.errors import ShotMillError
from shotmill.media.context import video_duration
from shotmill.media.storage import MediaStorage

logger = logging.getLogger(__name__)


def result_with_preview(result: Result, storage: MediaStorage) -> Result:
    """Derive video metadata and posters without rewriting existing history."""
    prefix = f"/media/{result.project_id}/"
    if not result.video_url.startswith(prefix):
        return result
    relative = result.video_url[len(prefix):]
    try:
        duration = video_duration(storage.resolve(result.project_id, relative))
    except (ShotMillError, ValueError):
        duration = None
    result = replace(result, metadata={**result.metadata, "durationSeconds": duration})
    if result.preview_url:
        return result
    try:
        poster = storage.video_thumbnail(result.project_id, relative)
    except (ShotMillError, ValueError):
        logger.warning("Could not create video poster for result %s", result.id)
        return result
    return replace(result, preview_url=storage.media_url(result.project_id, poster))

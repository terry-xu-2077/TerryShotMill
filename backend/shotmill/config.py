from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    api_version: str
    data_root: Path
    database_url: str
    auto_migrate: bool = True
    generation_workers: int = 1
    prompt_enhancement_workers: int = 1
    provider_poll_interval_seconds: float = 1.0
    provider_timeout_seconds: float = 600.0
    prompt_ai_base_url: str | None = None
    prompt_ai_api_key: str | None = None
    prompt_ai_model: str | None = None
    prompt_ai_supports_native_video: bool = False
    comfyui_base_url: str | None = None
    comfyui_root: Path | None = None
    comfyui_workflow_template: Path | None = None

    @property
    def projects_root(self) -> Path:
        return self.data_root / "projects"


def load_settings() -> Settings:
    data_root = Path(getenv("SHOTMILL_DATA_ROOT", ".shotmill")).expanduser().resolve()
    database_url = getenv("SHOTMILL_DATABASE_URL")
    if not database_url:
        database_url = f"sqlite+pysqlite:///{(data_root / 'shotmill.db').as_posix()}"

    comfyui_root = getenv("SHOTMILL_COMFYUI_ROOT")
    workflow_template = getenv("SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE")
    comfyui_base_url = getenv("SHOTMILL_COMFYUI_BASE_URL") or getenv("SHOTMILL_COMFYUI_ENDPOINT")
    prompt_ai_base_url = getenv("SHOTMILL_PROMPT_AI_BASE_URL") or comfyui_base_url
    return Settings(
        app_name="ShotMill",
        api_version="0.3",
        data_root=data_root,
        database_url=database_url,
        auto_migrate=_env_bool("SHOTMILL_AUTO_MIGRATE", True),
        generation_workers=max(1, int(getenv("SHOTMILL_GENERATION_WORKERS", "1"))),
        prompt_enhancement_workers=max(
            1, int(getenv("SHOTMILL_PROMPT_ENHANCEMENT_WORKERS", "1"))
        ),
        provider_poll_interval_seconds=float(getenv("SHOTMILL_PROVIDER_POLL_INTERVAL", "1.0")),
        provider_timeout_seconds=float(getenv("SHOTMILL_PROVIDER_TIMEOUT", "600")),
        prompt_ai_base_url=prompt_ai_base_url,
        prompt_ai_api_key=getenv("SHOTMILL_PROMPT_AI_API_KEY"),
        prompt_ai_model=getenv("SHOTMILL_PROMPT_AI_MODEL"),
        prompt_ai_supports_native_video=_env_bool("SHOTMILL_PROMPT_AI_SUPPORTS_VIDEO", False),
        comfyui_base_url=comfyui_base_url,
        comfyui_root=Path(comfyui_root).expanduser() if comfyui_root else None,
        comfyui_workflow_template=(
            Path(workflow_template).expanduser() if workflow_template else None
        ),
    )


settings = load_settings()

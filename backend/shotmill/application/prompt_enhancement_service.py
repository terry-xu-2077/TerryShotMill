from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from shotmill.domain.entities import AiPromptRevision, new_id, utcnow
from shotmill.domain.enums import PromptSource, TaskState
from shotmill.domain.providers import PromptAIProvider, PromptAIRequest, ResolvedMedia
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError, ShotMillError
from shotmill.media.resolver import MediaResolver
from shotmill.prompt_skills.base import SkillInput
from shotmill.prompt_skills.registry import PromptSkillRegistry


@dataclass(frozen=True, slots=True)
class EnhancementMedia:
    asset_id: str
    reference: str
    role: str | None = None


@dataclass(frozen=True, slots=True)
class EnhancementContextOptions:
    include_project_background: bool = False
    include_previous_task_summary: bool = False


@dataclass(frozen=True, slots=True)
class PromptEnhancementPreview:
    id: str
    created_at: datetime
    prompt: str
    target_skill: str
    skill_version: str
    provider_id: str | None
    model_id: str | None


class PromptEnhancementService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        provider: PromptAIProvider,
        skills: PromptSkillRegistry,
        media_resolver: MediaResolver,
    ) -> None:
        self.uow_factory = uow_factory
        self.provider = provider
        self.skills = skills
        self.media_resolver = media_resolver

    @staticmethod
    def _validate_provider_media(
        provider: PromptAIProvider,
        media: tuple[ResolvedMedia, ...],
    ) -> None:
        capability = provider.capability
        for item in media:
            if item.media_type == "image" and not capability.image_input:
                raise ShotMillError(
                    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                    "Prompt AI provider does not support image input",
                    422,
                )
            if item.media_type == "video" and not (
                capability.native_video_input or capability.sampled_video_frames
            ):
                raise ShotMillError(
                    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                    "Prompt AI provider does not support video input",
                    422,
                )
            if item.media_type == "audio" and not capability.audio_understanding:
                raise ShotMillError(
                    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                    "Prompt AI provider does not support audio understanding",
                    422,
                )

    async def enhance(
        self,
        project_id: str,
        task_id: str,
        *,
        target: str,
        user_prompt: str,
        media: tuple[EnhancementMedia, ...],
        context: EnhancementContextOptions,
        duration_seconds: float,
        mode: str,
        context_mode: str | None,
    ) -> AiPromptRevision:
        return await self._enhance(
            project_id,
            task_id,
            target=target,
            user_prompt=user_prompt,
            media=media,
            context=context,
            duration_seconds=duration_seconds,
            mode=mode,
            context_mode=context_mode,
            force_ai_source=False,
        )

    async def enhance_from_snapshot(
        self,
        project_id: str,
        task_id: str,
        *,
        target: str,
        user_prompt: str,
        media: tuple[EnhancementMedia, ...],
        include_project_background: bool,
        include_previous_task_summary: bool,
        project_background_snapshot: str | None,
        previous_task_summary_snapshot: str | None,
        duration_seconds: float,
        mode: str,
        context_mode: str | None,
        expected_task_revision: int | None = None,
        force_ai_source: bool = True,
    ) -> AiPromptRevision:
        return await self._enhance(
            project_id,
            task_id,
            target=target,
            user_prompt=user_prompt,
            media=media,
            context=EnhancementContextOptions(
                include_project_background=include_project_background,
                include_previous_task_summary=include_previous_task_summary,
            ),
            duration_seconds=duration_seconds,
            mode=mode,
            context_mode=context_mode,
            expected_task_revision=expected_task_revision,
            project_background_override=project_background_snapshot,
            previous_summary_override=previous_task_summary_snapshot,
            force_ai_source=force_ai_source,
        )

    async def _enhance(
        self,
        project_id: str,
        task_id: str,
        *,
        target: str,
        user_prompt: str,
        media: tuple[EnhancementMedia, ...],
        context: EnhancementContextOptions,
        duration_seconds: float,
        mode: str,
        context_mode: str | None,
        expected_task_revision: int | None = None,
        project_background_override: str | None = None,
        previous_summary_override: str | None = None,
        force_ai_source: bool = False,
    ) -> AiPromptRevision:
        clean_prompt = user_prompt.strip()
        if not clean_prompt:
            raise ShotMillError(
                "USER_PROMPT_REQUIRED",
                "User prompt is required for enhancement",
                422,
            )

        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")

            resolved: list[ResolvedMedia] = []
            for requested in media:
                asset = uow.assets.get(requested.asset_id)
                if asset is None or asset.project_id != project_id:
                    raise NotFoundError("ASSET_NOT_FOUND", f"Asset not found: {requested.asset_id}")
                resolved.append(
                    self.media_resolver.resolve(asset, requested.reference, requested.role)
                )

            project_background = project_background_override
            if project_background is None:
                if (
                    context.include_project_background
                    and project.use_description_for_ai_prompt
                    and project.description.strip()
                ):
                    project_background = project.description.strip()

            previous_summary = previous_summary_override
            if context.include_previous_task_summary and previous_summary is None:
                tasks = uow.tasks.list_by_project(project_id)
                previous = next(
                    (item for item in reversed(tasks) if item.display_order < task.display_order),
                    None,
                )
                if previous is not None:
                    previous_summary = (
                        previous.summary.strip()
                        or previous.user_intent.strip()
                        or previous.title.strip()
                        or None
                    )

        resolved_tuple = tuple(resolved)
        self._validate_provider_media(self.provider, resolved_tuple)
        skill = self.skills.get(target)
        message = skill.build(
            SkillInput(
                user_prompt=clean_prompt,
                project_background=project_background,
                previous_task_summary=previous_summary,
                duration_seconds=duration_seconds,
                mode=mode,
                context_mode=context_mode,
                media=resolved_tuple,
            )
        )
        response = await self.provider.enhance(
            PromptAIRequest(
                system_prompt=message.system_prompt,
                user_text=message.user_text,
                media=resolved_tuple,
            )
        )
        revision = AiPromptRevision(
            id=new_id("promptrev"),
            project_id=project_id,
            task_id=task_id,
            source_user_prompt=clean_prompt,
            output_prompt=response.text,
            asset_ids=[item.asset_id for item in media],
            project_background_used=project_background is not None,
            previous_task_summary_used=previous_summary is not None,
            target_skill=skill.id,
            skill_version=skill.version,
            provider_profile_id=response.provider_id,
            model=response.model_id,
            previous_task_summary_snapshot=previous_summary,
        )
        with self.uow_factory() as uow:
            current = uow.tasks.get(task_id)
            if current is None or current.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            if expected_task_revision is not None and current.revision != expected_task_revision:
                raise ShotMillError(
                    "PROMPT_JOB_STALE",
                    "Task changed after this prompt job was queued",
                    409,
                )
            old_final = current.final_prompt
            current.ai_prompt = response.text
            if force_ai_source:
                current.prompt_source = PromptSource.AI
            if current.prompt_source == PromptSource.AI:
                current.final_prompt = response.text
            current.approved_prompt_source = None
            current.approved_prompt_hash = None
            current.approved_at = None
            current.approved_revision_id = None
            current.state = TaskState.PROMPT_READY if current.final_prompt else TaskState.DRAFT
            current.revision += 1
            current.updated_at = utcnow()
            uow.prompt_revisions.add(revision)
            uow.tasks.update(current)
            if old_final != current.final_prompt:
                uow.contexts.mark_stale_by_source(current.id)
        return revision

    async def preview(
        self,
        project_id: str,
        *,
        target: str,
        user_prompt: str,
        media: tuple[EnhancementMedia, ...],
        context: EnhancementContextOptions,
        duration_seconds: float,
        mode: str,
        context_mode: str | None,
        previous_task_id: str | None = None,
    ) -> PromptEnhancementPreview:
        """Enhance an unsaved task draft without creating a Task or revision."""
        clean_prompt = user_prompt.strip()
        if not clean_prompt:
            raise ShotMillError(
                "USER_PROMPT_REQUIRED",
                "User prompt is required for enhancement",
                422,
            )

        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")

            resolved: list[ResolvedMedia] = []
            for requested in media:
                asset = uow.assets.get(requested.asset_id)
                if asset is None or asset.project_id != project_id:
                    raise NotFoundError("ASSET_NOT_FOUND", f"Asset not found: {requested.asset_id}")
                resolved.append(
                    self.media_resolver.resolve(asset, requested.reference, requested.role)
                )

            project_background = None
            if (
                context.include_project_background
                and project.use_description_for_ai_prompt
                and project.description.strip()
            ):
                project_background = project.description.strip()

            previous_summary = None
            if context.include_previous_task_summary and not previous_task_id:
                raise ShotMillError(
                    "PREVIOUS_TASK_REQUIRED",
                    "Previous task is required when its summary is enabled",
                    422,
                )
            if context.include_previous_task_summary and previous_task_id:
                previous = uow.tasks.get(previous_task_id)
                if previous is None or previous.project_id != project_id:
                    raise NotFoundError("TASK_NOT_FOUND", "Previous task not found")
                previous_summary = (
                    previous.summary.strip()
                    or previous.user_intent.strip()
                    or previous.title.strip()
                    or None
                )

        resolved_tuple = tuple(resolved)
        self._validate_provider_media(self.provider, resolved_tuple)
        skill = self.skills.get(target)
        message = skill.build(
            SkillInput(
                user_prompt=clean_prompt,
                project_background=project_background,
                previous_task_summary=previous_summary,
                duration_seconds=duration_seconds,
                mode=mode,
                context_mode=context_mode,
                media=resolved_tuple,
            )
        )
        response = await self.provider.enhance(
            PromptAIRequest(
                system_prompt=message.system_prompt,
                user_text=message.user_text,
                media=resolved_tuple,
            )
        )
        return PromptEnhancementPreview(
            id=new_id("promptpreview"),
            created_at=utcnow(),
            prompt=response.text,
            target_skill=skill.id,
            skill_version=skill.version,
            provider_id=response.provider_id,
            model_id=response.model_id,
        )

    def list_revisions(self, project_id: str, task_id: str) -> list[AiPromptRevision]:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            return uow.prompt_revisions.list_by_task(task_id)

    def select_revision(self, project_id: str, task_id: str, revision_id: str) -> AiPromptRevision:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            revision = uow.prompt_revisions.get(revision_id)
            if revision is None or revision.task_id != task_id:
                raise NotFoundError("PROMPT_REVISION_NOT_FOUND", "Prompt revision not found")
            old_final = task.final_prompt
            task.ai_prompt = revision.output_prompt
            if task.prompt_source == PromptSource.AI:
                task.final_prompt = revision.output_prompt
            task.approved_prompt_source = None
            task.approved_prompt_hash = None
            task.approved_at = None
            task.approved_revision_id = None
            task.revision += 1
            task.updated_at = utcnow()
            uow.tasks.update(task)
            if old_final != task.final_prompt:
                uow.contexts.mark_stale_by_source(task.id)
            return revision

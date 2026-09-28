"""Import a verified project as an independent project in one publication transaction."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import BinaryIO

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_import_media import bind_project_import_media
from shotmill.application.project_import_preflight import preflight_project_import
from shotmill.application.project_transfer_identity import remap_project_identity
from shotmill.application.project_transfer_validation import validate_project_transfer_graph
from shotmill.domain.repositories import UnitOfWork


@dataclass(frozen=True)
class ProjectImportOutcome:
    project_id: str
    provider_requirements: list[dict]


class ProjectImportService:
    def __init__(self, factory: Callable[[], UnitOfWork], library: FileLibrary):
        self.factory = factory
        self.library = library

    def import_package(self, stream: BinaryIO) -> ProjectImportOutcome:
        staging = self.library.storage.managed.resolve("staging")
        staging.mkdir(parents=True, exist_ok=True)
        with preflight_project_import(stream, staging_parent=staging) as package:
            identity = remap_project_identity(package.source)
            with self.factory() as uow:
                uow.reserve_write()
                source = bind_project_import_media(uow, self.library, identity, package.files)
                validate_project_transfer_graph(source)
                uow.projects.add(replace(source.project, cover_asset_id=None))
                uow.projects.set_transfer_requirements(
                    source.project.id, package.provider_requirements,
                )
                for asset in source.assets:
                    uow.assets.add(asset)
                for scene in source.scenes:
                    uow.story_structure.add_scene(scene)
                for task in source.tasks:
                    uow.tasks.add(replace(task, primary_result_id=None, approved_revision_id=None))
                    uow.tasks.set_generation_configuration_required(task.id, True)
                for placement in source.placements:
                    uow.story_structure.place_task(source.project.id, placement)
                for job in source.jobs:
                    uow.jobs.add(job)
                for result in source.results:
                    uow.results.add(result)
                for revision in source.prompt_revisions:
                    uow.prompt_revisions.add(revision)
                for batch in source.prompt_batches:
                    uow.prompt_batches.add(batch)
                for job in source.prompt_jobs:
                    uow.prompt_jobs.add(job)
                for task in source.tasks:
                    uow.tasks.update(task)
                    uow.contexts.replace_for_target(
                        task.id,
                        [link for link in source.contexts if link.target_task_id == task.id],
                    )
                uow.projects.update(source.project)
            return ProjectImportOutcome(source.project.id, package.provider_requirements)

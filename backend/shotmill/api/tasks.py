from fastapi import APIRouter, status

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import EditorPreferencePatch, TaskReorderRequest, TaskSaveRequest
from shotmill.application.task_service import SaveTaskAsset, SaveTaskData
from shotmill.frontend_adapter.models import EditorPreference, TaskEditorView, TaskSummary

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["tasks"])


def _command(payload: TaskSaveRequest) -> SaveTaskData:
    return SaveTaskData(
        title=payload.title,
        summary=payload.summary,
        script_source=payload.script_source,
        user_intent=payload.user_intent,
        user_prompt=payload.user_prompt,
        ai_prompt=payload.ai_enhanced_prompt,
        prompt_source=payload.prompt_source,
        duration_seconds=payload.duration_seconds,
        generation=payload.generation.model_dump(by_alias=True, exclude_none=False),
        asset_bindings=tuple(
            SaveTaskAsset(asset_id=item.asset_id, reference=item.reference, role=item.role)
            for item in payload.asset_bindings
        ),
        user_view_mode=payload.editor_preference.user_view_mode,
        ai_view_mode=payload.editor_preference.ai_view_mode,
        revision=payload.revision,
    )


@router.get("/{task_id}/editor", response_model=TaskEditorView)
def get_task_editor(
    project_id: str,
    task_id: str,
    container: ContainerDep,
) -> TaskEditorView:
    return container.workspace_query.task_editor(project_id, task_id)


@router.post("", response_model=TaskSummary, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: str,
    payload: TaskSaveRequest,
    container: ContainerDep,
) -> TaskSummary:
    task = container.task_service.create(project_id, _command(payload))
    return container.workspace_query.task_summary(project_id, task.id)


@router.patch("/{task_id}", response_model=TaskSummary)
def update_task(
    project_id: str,
    task_id: str,
    payload: TaskSaveRequest,
    container: ContainerDep,
) -> TaskSummary:
    container.task_service.update(project_id, task_id, _command(payload))
    return container.workspace_query.task_summary(project_id, task_id)


@router.patch("/{task_id}/editor-preference", response_model=EditorPreference)
def update_editor_preference(
    project_id: str,
    task_id: str,
    payload: EditorPreferencePatch,
    container: ContainerDep,
) -> EditorPreference:
    preference = container.task_service.update_editor_preference(
        project_id, task_id, **payload.model_dump(exclude_unset=True)
    )
    return EditorPreference(**preference)


@router.post("/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_tasks(
    project_id: str,
    payload: TaskReorderRequest,
    container: ContainerDep,
) -> None:
    container.task_service.reorder(project_id, payload.task_ids)

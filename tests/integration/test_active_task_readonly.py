from copy import deepcopy

import pytest
from shotmill.domain.enums import TaskState
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


@pytest.mark.parametrize('state', [TaskState.QUEUED, TaskState.RUNNING])
def test_active_video_task_rejects_content_edits_but_allows_reading_and_view_preferences(
    client, state,
):
    project = _project(client)['id']
    task = _task(client, project, '只读镜头', '原始提示词')['id']
    root = f'/api/v1/projects/{project}/tasks/{task}'
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    assert client.post(root + '/generation', json={}).status_code == 202
    with service.uow_factory() as uow:
        current = uow.tasks.get(task)
        current.state = state
        uow.tasks.update(current)
    before = client.get(root + '/editor').json()
    response = client.patch(root, json={**before, 'userPrompt': '不允许写入'})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'TASK_BUSY'
    assert client.get(root + '/editor').json() == before
    response = client.patch(root + '/editor-preference', json={'userViewMode': 'text'})
    assert response.status_code == 200
    expected = deepcopy(before)
    expected['editorPreference']['userViewMode'] = 'text'
    assert client.get(root + '/editor').json() == expected

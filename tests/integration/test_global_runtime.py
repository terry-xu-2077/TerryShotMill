from test_batch_review_api import _project, _task, _wait_prompt_batch
from test_prompt_batch_recovery import HeldQueue
from test_video_queue_cancel import _submit


def test_global_runtime_groups_all_projects_and_preserves_job_ownership(client):
    first = _project(client)['id']
    second = _project(client)['id']
    empty = _project(client)['id']
    a = _task(client, first, '项目一镜头', '雨夜街道')['id']
    b = _task(client, second, '项目二镜头', '清晨海岸')['id']
    batch = client.post(f'/api/v1/projects/{first}/prompt-enhancement-batches',
                        json={'taskIds': [a]}).json()['batchId']
    _wait_prompt_batch(client, first, batch)
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job = _submit(client, second, b)
    response = client.get('/api/v1/projects/runtime')
    assert response.status_code == 200, response.text
    groups = {item['project']['id']: item['runtime'] for item in response.json()}
    assert set(groups) == {first, second, empty}
    assert groups[first]['promptBatches'][0]['items'][0]['taskId'] == a
    assert groups[first]['videoJobs'] == []
    assert groups[second]['promptBatches'] == []
    assert groups[second]['videoJobs'][0]['id'] == job
    assert groups[second]['videoJobs'][0]['state'] == 'queued'
    assert groups[empty]['videoJobs'] == []
    client.post(f'/api/v1/projects/{second}/video-generation-queue/cancel', json={'jobIds': [job]})
    changed = client.get('/api/v1/projects/runtime').json()
    item = next(item for item in changed if item['project']['id'] == second)
    assert item['runtime']['videoJobs'][0]['state'] == 'cancelled'

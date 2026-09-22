from shotmill.domain.enums import JobStatus
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_prompt_preview_is_read_only_and_matches_submission_rules(client, providers):
    project = _project(client)['id']
    ready = _task(client, project, '可执行', '动作描述')['id']
    empty = client.post(f'/api/v1/projects/{project}/tasks', json={'title': '空任务'}).json()['id']
    busy = _task(client, project, '正在增强', '等待增强')['id']
    service = client.app.state.container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    root = f'/api/v1/projects/{project}/prompt-enhancement-batches'
    assert client.post(root, json={'taskIds': [busy]}).status_code == 202
    def persisted_state():
        with service.uow_factory() as uow:
            return (uow.projects.get(project), uow.tasks.list_by_project(project),
                    uow.prompt_jobs.get(queue.jobs[0]))

    before = persisted_state()
    preview = client.post(root + '/eligibility', json={'taskIds': [busy, ready, empty, ready]})
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        'eligibleTaskIds': [ready],
        'skipped': [
            {'taskId': empty, 'reason': 'empty-prompt', 'message': '缺少用户提示词'},
            {'taskId': busy, 'reason': 'busy', 'message': '正在增强或排队'},
        ],
    }
    assert persisted_state() == before
    assert len(queue.jobs) == 1
    assert not providers[0].requests
    with service.uow_factory() as uow:
        job = uow.prompt_jobs.get(queue.jobs[0])
        job.status = JobStatus.RUNNING
        uow.prompt_jobs.update(job)
    assert client.post(root + '/eligibility', json={'taskIds': []}).json() == preview.json()
    submitted = client.post(root, json={'taskIds': [busy, ready, empty]}).json()
    assert {item['taskId']: item['state'] for item in submitted['items']} == {
        ready: 'queued', empty: 'failed', busy: 'skipped',
    }
    assert len(queue.jobs) == 2


def test_prompt_preview_respects_selection_and_rejects_foreign_tasks(client):
    project = _project(client)['id']
    first = _task(client, project, '任务一', '第一条')['id']
    second = _task(client, project, '任务二', '第二条')['id']
    other = _project(client)['id']
    foreign = _task(client, other, '其他项目任务', '描述')['id']
    root = f'/api/v1/projects/{project}/prompt-enhancement-batches/eligibility'
    assert client.post(root, json={'taskIds': [second]}).json() == {
        'eligibleTaskIds': [second], 'skipped': [],
    }
    assert client.post(root, json={'taskIds': [second, first]}).json()['eligibleTaskIds'] == [
        first, second,
    ]
    assert client.post(root, json={'taskIds': [foreign]}).status_code == 404
    assert client.post(root, json={'taskIds': ['missing']}).status_code == 404

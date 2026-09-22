from copy import deepcopy

import pytest


def test_view_preferences_are_independent_of_task_content_and_review(client):
    project = client.post('/api/v1/projects', json={'title': '显示偏好'}).json()['id']
    root = f'/api/v1/projects/{project}/tasks'
    task = client.post(root, json={
        'title': '镜头一', 'userPrompt': '原始描述', 'aiEnhancedPrompt': '增强描述',
        'promptSource': 'ai',
    }).json()['id']
    other = client.post(root, json={'title': '镜头二'}).json()['id']
    approved = client.post(f'{root}/{task}/prompt-review', json={'action': 'approve'})
    assert approved.status_code == 200
    before = client.get(f'{root}/{task}/editor').json()
    review_response = client.get(f'/api/v1/projects/{project}/prompt-review-state')
    assert review_response.status_code == 200
    review_before = review_response.json()
    response = client.patch(f'{root}/{task}/editor-preference', json={'userViewMode': 'text'})
    assert response.status_code == 200, response.text
    assert response.json() == {'userViewMode': 'text', 'aiViewMode': 'visual'}
    response = client.patch(f'{root}/{task}/editor-preference', json={'aiViewMode': 'text'})
    assert response.json() == {'userViewMode': 'text', 'aiViewMode': 'text'}
    after = client.get(f'{root}/{task}/editor').json()
    expected = deepcopy(before)
    expected['editorPreference'] = response.json()
    assert after == expected
    assert client.get(f'/api/v1/projects/{project}/prompt-review-state').json() == review_before
    assert client.get(f'{root}/{other}/editor').json()['editorPreference'] == {
        'userViewMode': 'visual', 'aiViewMode': 'visual',
    }
    foreign = client.post('/api/v1/projects', json={'title': '其他项目'}).json()['id']
    assert client.patch(f'/api/v1/projects/{foreign}/tasks/{task}/editor-preference',
                        json={'userViewMode': 'visual'}).status_code == 404


@pytest.mark.parametrize('payload', [{'userViewMode': 'invalid'}, {'aiViewMode': None}])
def test_invalid_preference_is_rejected(client, payload):
    assert client.patch('/api/v1/projects/missing/tasks/missing/editor-preference',
                        json=payload).status_code == 422

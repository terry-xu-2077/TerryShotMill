import asyncio

import httpx
import pytest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def test_video_provider_resumes_original_remote_job_without_upload_or_submission():
    calls = []
    states = iter(['queued', 'running', 'completed'])

    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.method == 'GET'
        if '/files/' in request.url.path:
            return httpx.Response(200, content=b'existing-video',
                                  headers={'content-type': 'video/mp4'})
        return httpx.Response(200, json={
            'status': next(states), 'promptId': 'original-remote',
            'results': [{'filename': 'original.mp4'}],
        })

    provider = ComfyUIVideoGenerationProvider(
        'http://original-server', None, poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.resume('saved-job'))
    assert provider.capability.job_resumption
    assert result.provider_job_id == 'original-remote'
    assert result.outputs[0].content == b'existing-video'
    assert calls == [('GET', '/shotmill/v1/jobs/saved-job')] * 3 + [
        ('GET', '/shotmill/v1/results/saved-job/files/0'),
    ]


@pytest.mark.parametrize(('status', 'body', 'code'), [
    (404, {}, 'SHOTMILL_BRIDGE_JOB_NOT_FOUND'),
    (200, {'status': 'not_found'}, 'SHOTMILL_BRIDGE_JOB_NOT_FOUND'),
    (200, {'status': 'failed', 'error': 'original failure'}, 'SHOTMILL_BRIDGE_JOB_FAILED'),
    (200, {'status': 'completed', 'promptId': 'p', 'results': []}, 'SHOTMILL_BRIDGE_NO_OUTPUT'),
    (200, {'status': 'running'}, 'SHOTMILL_BRIDGE_TIMEOUT'),
    (200, [], 'SHOTMILL_BRIDGE_INVALID_RESPONSE'),
])
def test_video_provider_resume_failure_never_resubmits(status, body, code):
    calls = []

    def handler(request):
        calls.append(request.method)
        assert request.method == 'GET'
        return httpx.Response(status, json=body)

    provider = ComfyUIVideoGenerationProvider(
        'http://original-server', None, poll_interval_seconds=0.001, timeout_seconds=0.005,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ShotMillError) as error:
        asyncio.run(provider.resume('saved-job'))
    assert error.value.code == code
    assert calls


def test_video_provider_resume_rejects_malformed_json_without_resubmission():
    def handler(request):
        assert request.method == 'GET'
        return httpx.Response(200, content=b'not-json')

    provider = ComfyUIVideoGenerationProvider(
        'http://original-server', None, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ShotMillError) as error:
        asyncio.run(provider.resume('saved-job'))
    assert error.value.code == 'SHOTMILL_BRIDGE_INVALID_RESPONSE'

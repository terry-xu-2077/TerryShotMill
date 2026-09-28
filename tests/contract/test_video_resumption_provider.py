import asyncio
import hashlib

import httpx
import pytest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


@pytest.mark.parametrize("checksum", ["valid", "0" * 64, "malformed", None])
def test_download_checks_advertised_digest_and_marks_legacy_unverified(checksum):
    content = b"original-video"
    digest = hashlib.sha256(content).hexdigest()
    advertised = digest if checksum == "valid" else checksum

    def handler(request):
        assert request.method == "GET"
        if "/files/" in request.url.path:
            headers = {"X-Content-SHA256": advertised} if advertised is not None else {}
            return httpx.Response(200, content=content, headers=headers)
        return httpx.Response(200, json={
            "status": "completed", "promptId": "original",
            "results": [{"filename": "clip.mp4"}],
        })

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
    )
    if checksum not in ("valid", None):
        with pytest.raises(ShotMillError) as error:
            asyncio.run(provider.resume("saved-job"))
        assert error.value.code == "COMFYUI_DOWNLOAD_CHECKSUM_MISMATCH"
    else:
        response = asyncio.run(provider.resume("saved-job"))
        output = response.outputs[0]
        assert output.metadata["sha256"] == digest
        assert output.metadata["transferVerified"] is (checksum == "valid")
        response.close()


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
    assert result.outputs[0].content.read() == b'existing-video'
    result.close()
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


@pytest.mark.parametrize('failure', ['disconnect', 'timeout', 'unavailable'])
def test_lan_reconnect_collects_original_job_after_poll_and_download_failures(failure):
    calls = []
    attempts = {'status': 0, 'file': 0}
    progress = []

    def handler(request):
        assert request.method == 'GET'
        calls.append(request.url.path)
        kind = 'file' if '/files/' in request.url.path else 'status'
        attempts[kind] += 1
        if attempts[kind] == 1:
            if failure == 'unavailable':
                return httpx.Response(503)
            error = httpx.ConnectError if failure == 'disconnect' else httpx.ReadTimeout
            raise error('LAN offline', request=request)
        if kind == 'file':
            return httpx.Response(
                200, content=b'original-result', headers={'content-type': 'video/mp4'}
            )
        return httpx.Response(200, json={
            'status': 'completed', 'promptId': 'original',
            'results': [{'filename': 'original.mp4'}],
        })

    provider = ComfyUIVideoGenerationProvider(
        'http://desktop', None, transport=httpx.MockTransport(handler), poll_interval_seconds=0.1,
        timeout_seconds=0.01,
    )

    async def report(value):
        progress.append(value)

    provider.set_progress_callback(report)
    response = asyncio.run(provider.resume('original-job'))
    assert response.provider_job_id == 'original'
    assert response.outputs[0].content.read() == b'original-result'
    response.close()
    assert attempts == {'status': 2, 'file': 2}
    assert any(item.get('connectionState') == 'reconnecting' for item in progress)
    assert any(item.get('remoteState') == 'completed' for item in progress)


def test_lan_wait_can_be_cancelled_without_stopping_remote_job():
    calls = []
    reached = asyncio.Event()

    def handler(request):
        calls.append(request.method)
        reached.set()
        raise httpx.ConnectError('LAN offline', request=request)

    provider = ComfyUIVideoGenerationProvider(
        'http://desktop', None, transport=httpx.MockTransport(handler)
    )

    async def run():
        task = asyncio.create_task(provider.resume('original-job'))
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert calls == ['GET']


@pytest.mark.parametrize('checksum', [None, '0' * 64])
def test_upload_rejects_missing_or_incorrect_checksum(tmp_path, checksum):
    from shotmill.domain.providers import ResolvedMedia, VideoGenerationRequest

    media = tmp_path / 'asset.png'
    media.write_bytes(b'original')
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert b'name="sha256"' in request.content
        return httpx.Response(200, json={
            'asset': {'relativePath': 'remote/asset.png', 'sha256': checksum},
        })

    provider = ComfyUIVideoGenerationProvider('http://desktop', None)
    request = VideoGenerationRequest(
        'j', 'p', 't', 'prompt', (ResolvedMedia('a', '<Picture 1>', None, 'image', media),), {},
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await provider._upload_assets(client, request, 'http://desktop')

    with pytest.raises(ShotMillError) as error:
        asyncio.run(run())
    assert error.value.code == 'COMFYUI_UPLOAD_CHECKSUM_MISMATCH'
    assert calls == ['/shotmill/v1/assets']

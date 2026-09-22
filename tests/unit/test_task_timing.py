from datetime import UTC, datetime, timedelta

from shotmill.domain.entities import Job, PromptEnhancementJob
from shotmill.domain.enums import JobStatus
from shotmill.frontend_adapter.timing import task_timing


def job(start, end, status=JobStatus.COMPLETED):
    created = datetime(2026, 9, 21, tzinfo=UTC)
    return Job(
        id="j",
        project_id="p",
        task_id="t",
        status=status,
        task_content_snapshot={},
        final_prompt_snapshot="",
        assets_snapshot=[],
        generation_profile_snapshot={},
        provider_profile_snapshot={},
        params_snapshot={},
        context_snapshot={},
        submitted_at=created,
        started_at=created + timedelta(seconds=start) if start else None,
        completed_at=created + timedelta(seconds=end) if end else None,
    )


def test_execution_time_excludes_queue_time_and_stops_at_completion():
    result = task_timing([job(10, 322)], [])
    assert result.video_seconds == 312
    assert result.video_queue_seconds == 10
    assert result.video_running is False


def test_unstarted_job_has_no_fabricated_execution_time():
    result = task_timing([job(None, None, JobStatus.QUEUED)], [])
    assert result.video_seconds is None


def test_missing_historical_timing_stays_unknown():
    result = task_timing([], [])
    assert result.video_seconds is None
    assert result.prompt_seconds is None


def prompt_job(status, start, end):
    created = datetime(2026, 9, 21, tzinfo=UTC)
    return PromptEnhancementJob(
        id="pjob", batch_id="b", project_id="p", task_id="t", status=status,
        source_snapshot={}, context_snapshot={}, provider_profile_snapshot={},
        target_skill="test", created_at=created,
        started_at=created + timedelta(seconds=start) if start is not None else None,
        finished_at=created + timedelta(seconds=end) if end is not None else None,
    )


def test_failed_prompt_attempt_has_separate_execution_and_queue_times():
    result = task_timing([], [], [prompt_job(JobStatus.FAILED, 12, 47)])
    assert result.prompt_seconds == 35
    assert result.prompt_queue_seconds == 12
    assert result.prompt_running is False


def test_cancelled_before_start_has_queue_time_but_no_execution_time():
    result = task_timing([], [], [prompt_job(JobStatus.CANCELLED, None, 17)])
    assert result.prompt_seconds is None
    assert result.prompt_queue_seconds == 17


def test_live_prompt_timing_exposes_measurement_time_for_display(monkeypatch):
    from shotmill.frontend_adapter import timing

    now = datetime(2026, 9, 21, tzinfo=UTC) + timedelta(seconds=65)
    monkeypatch.setattr(timing, "utcnow", lambda: now)
    result = task_timing([], [], [prompt_job(JobStatus.RUNNING, 5, None)])
    assert result.prompt_running is True
    assert result.prompt_seconds == 60
    assert result.prompt_queue_seconds == 5
    assert result.measured_at == now

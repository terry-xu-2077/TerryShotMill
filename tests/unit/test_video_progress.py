from shotmill.providers.video_generation.progress import StepProgress


def test_progress_is_scoped_and_estimates_from_observed_steps():
    tracker = StepProgress("mine", {"1": {"class_type": "SamplerCustomAdvanced"}})
    assert (
        tracker.consume(
            {"type": "progress", "data": {"prompt_id": "other", "value": 1, "max": 10}}, 0
        )
        is None
    )
    tracker.consume({"type": "executing", "data": {"prompt_id": "mine", "node": "1"}}, 0)
    first = tracker.consume(
        {"type": "progress", "data": {"prompt_id": "mine", "node": "1", "value": 1, "max": 10}}, 10
    )
    assert first["percent"] == 10
    assert first["remainingSeconds"] == 90
    second = tracker.consume(
        {"type": "progress", "data": {"prompt_id": "mine", "node": "1", "value": 3, "max": 10}}, 30
    )
    assert second["remainingSeconds"] == 70
    next_stage = tracker.consume(
        {"type": "executing", "data": {"prompt_id": "mine", "node": "2"}}, 100
    )
    assert next_stage["percent"] is None
    assert next_stage["stages"][0]["seconds"] == 100

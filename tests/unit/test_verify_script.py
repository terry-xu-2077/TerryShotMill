from pathlib import Path

from scripts import verify


def test_frontend_stages_use_direct_node_without_command_shell():
    scripts = ["typescript/bin/tsc", "vitest/vitest.mjs", "vite/bin/vite.js"]
    for stage, script in zip(verify.FRONTEND_STAGES, scripts, strict=True):
        assert Path(stage.command[0]).stem.lower() == "node"
        assert Path(stage.command[1]) == verify.FRONTEND / "node_modules" / script
        assert stage.cwd == verify.FRONTEND
    assert "-b" in verify.FRONTEND_STAGES[0].command
    assert "run" in verify.FRONTEND_STAGES[1].command
    assert "build" in verify.FRONTEND_STAGES[2].command


def test_optional_pytest_stage_only_exists_when_keyword_has_matching_tests(
    tmp_path: Path, monkeypatch
) -> None:
    integration = tmp_path / "tests" / "integration"
    integration.mkdir(parents=True)
    (integration / "test_assets.py").write_text(
        "def test_asset_import():\n    assert True\n", encoding="utf-8"
    )
    monkeypatch.setattr(verify, "ROOT", tmp_path)

    assert (
        verify.optional_pytest_stage("scheduler integration", "tests/integration", "scheduler")
        is None
    )

    (integration / "test_scheduler.py").write_text(
        "def test_scheduler_recovers():\n    assert True\n", encoding="utf-8"
    )
    stage = verify.optional_pytest_stage("scheduler integration", "tests/integration", "scheduler")
    assert stage is not None
    assert stage.command[-1] == "scheduler"

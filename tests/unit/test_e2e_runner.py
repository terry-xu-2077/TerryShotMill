from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from scripts import run_e2e


def test_windows_e2e_cleanup_stops_owned_python_launcher_tree():
    process = Mock(pid=1234)
    process.poll.return_value = None
    with patch.object(run_e2e.sys, "platform", "win32"), patch.object(
        run_e2e.subprocess, "run", return_value=Mock(returncode=0)
    ) as execute:
        run_e2e.stop_process(process)
    execute.assert_called_once_with(
        ["taskkill.exe", "/PID", "1234", "/T", "/F"],
        check=False, stdout=run_e2e.subprocess.DEVNULL, stderr=run_e2e.subprocess.DEVNULL,
    )
    process.terminate.assert_not_called()
    process.wait.assert_called_once_with(timeout=5)


def sharing_violation():
    error = PermissionError("Windows file handle is still closing")
    error.winerror = 32
    return error


def test_temporary_cleanup_retries_only_windows_sharing_violation():
    directory = Mock()
    directory.cleanup.side_effect = [sharing_violation(), None]
    with patch.object(run_e2e.sys, "platform", "win32"), patch.object(run_e2e.time, "sleep"):
        run_e2e.cleanup_data_root(directory)
    assert directory.cleanup.call_count == 2


def test_temporary_cleanup_reports_persistent_lock_without_hiding_failure():
    directory = Mock()
    directory.cleanup.side_effect = sharing_violation()
    with patch.object(run_e2e.sys, "platform", "win32"), patch.object(
        run_e2e.time, "monotonic", side_effect=[0, 3],
    ), pytest.raises(PermissionError):
        run_e2e.cleanup_data_root(directory)


def test_temporary_cleanup_does_not_retry_other_permission_errors():
    directory = Mock()
    directory.cleanup.side_effect = PermissionError("access denied")
    with patch.object(run_e2e.time, "sleep") as sleep, pytest.raises(PermissionError):
        run_e2e.cleanup_data_root(directory)
    sleep.assert_not_called()

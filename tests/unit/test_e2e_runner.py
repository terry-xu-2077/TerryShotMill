from __future__ import annotations

from unittest.mock import Mock, patch

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

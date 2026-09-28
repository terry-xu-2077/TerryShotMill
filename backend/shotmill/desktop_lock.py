"""An OS-owned lock prevents two desktop runtimes scheduling the same database."""

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def desktop_data_lock(data_root: Path):
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / "desktop.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("该数据目录已由另一个 ShotMill 窗口使用，请勿重复启动。") from exc
        # Closing the handle releases the lock, including abnormal process exit.
        # Do not unlink: another process may already hold the same file open.
        yield

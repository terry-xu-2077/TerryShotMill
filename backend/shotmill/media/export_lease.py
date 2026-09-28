"""OS-owned lease for a private export; process death releases ownership."""

import os
from contextlib import contextmanager
from pathlib import Path

SIGNATURE = b"\0ShotMill project export v1\n"


@contextmanager
def export_lease(path: Path, *, create: bool = False):
    with path.open("x+b" if create else "r+b") as stream:
        if create:
            stream.write(SIGNATURE)
            stream.flush()
            os.fsync(stream.fileno())
        else:
            if stream.read(len(SIGNATURE) + 1) != SIGNATURE:
                raise ValueError("Unknown export lease")
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
        else:
            yield True

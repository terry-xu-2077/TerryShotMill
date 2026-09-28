# PyInstaller onedir runtime. Build from the repository root:
# .venv/Scripts/python.exe -m PyInstaller packaging/shotmill-backend.spec
#   --distpath .artifacts/windows-runtime --workpath .artifacts/pyinstaller
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
package = root / "backend" / "shotmill"
# Explicit build input, not an accidental executable found on the developer PATH.
ffmpeg_root = Path(os.environ["SHOTMILL_FFMPEG_ROOT"]).resolve(strict=True)
for required in ("bin/ffmpeg.exe", "bin/ffprobe.exe", "LICENSE", "README.txt"):
    if not (ffmpeg_root / required).is_file():
        raise ValueError(f"Missing FFmpeg distribution resource: {required}")
datas = [
    (str(ffmpeg_root / "LICENSE"), "licenses/ffmpeg"),
    (str(ffmpeg_root / "README.txt"), "licenses/ffmpeg"),
    (str(package / "providers" / "video_generation" / "workflows"),
     "shotmill/providers/video_generation/workflows"),
]
for source in (package / "persistence" / "migrations").rglob("*"):
    if source.is_file() and source.suffix in {".py", ".mako"}:
        datas.append((str(source), str(Path("shotmill") / source.parent.relative_to(package))))
analysis = Analysis(
    [str(package / "desktop_runtime.py")],
    pathex=[str(root / "backend")],
    datas=datas,
    binaries=[(str(ffmpeg_root / "bin" / name), "media-tools")
              for name in ("ffmpeg.exe", "ffprobe.exe")],
    hiddenimports=collect_submodules("uvicorn") + ["sqlalchemy.dialects.sqlite"],
    excludes=["pytest", "tkinter"],
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name="shotmill-backend", console=True, upx=False,
)
bundle = COLLECT(
    executable, analysis.binaries, analysis.datas,
    name="shotmill-backend", upx=False,
)

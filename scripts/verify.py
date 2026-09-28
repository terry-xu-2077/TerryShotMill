from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
NODE = shutil.which("node") or "node"


@dataclass(frozen=True, slots=True)
class Stage:
    name: str
    command: tuple[str, ...]
    cwd: Path = ROOT
    capture_output: bool = True


def python_stage(name: str, *args: str) -> Stage:
    return Stage(name, (sys.executable, *args))


BACKEND = (
    python_stage("backend lint", "-m", "ruff", "check", "backend", "tests", "scripts"),
    python_stage("backend tests", "-m", "pytest", "-q", "tests/unit", "tests/integration"),
)
FRONTEND_STAGES = (
    Stage("frontend typecheck", (
        NODE, str(FRONTEND / "node_modules/typescript/bin/tsc"), "-b", "--pretty", "false",
    ), FRONTEND),
    Stage("frontend tests", (
        NODE, str(FRONTEND / "node_modules/vitest/vitest.mjs"), "run",
    ), FRONTEND),
    Stage("frontend build", (
        NODE, str(FRONTEND / "node_modules/vite/bin/vite.js"), "build",
    ), FRONTEND),
)
E2E = (
    Stage(
        "desktop and mobile e2e",
        (sys.executable, str(ROOT / "scripts" / "run_e2e.py")),
        ROOT,
        capture_output=False,
    ),
)


def optional_pytest_stage(name: str, folder: str, keyword: str) -> Stage | None:
    files = tuple((ROOT / folder).rglob("test_*.py"))
    normalized_keyword = keyword.casefold()
    matching_files = tuple(
        path
        for path in files
        if normalized_keyword in path.name.casefold()
        or normalized_keyword in path.read_text(encoding="utf-8", errors="ignore").casefold()
    )
    if not matching_files:
        return None
    return python_stage(name, "-m", "pytest", "-q", folder, "-k", keyword)


def stages_for(area: str, full: bool) -> list[Stage]:
    if full:
        stages = [*BACKEND, *FRONTEND_STAGES]
        contract = optional_pytest_stage("provider contracts", "tests/contract", "provider")
        scheduler = optional_pytest_stage("scheduler integration", "tests/integration", "scheduler")
        stages.extend(stage for stage in (contract, scheduler) if stage is not None)
        stages.extend(E2E)
        return stages

    if area == "backend":
        return list(BACKEND)
    if area in {"frontend", "ui"}:
        return list(FRONTEND_STAGES)
    if area == "e2e":
        return list(E2E)
    if area == "providers":
        stage = optional_pytest_stage("provider contracts", "tests/contract", "provider")
        return [stage] if stage else []
    if area == "scheduler":
        stage = optional_pytest_stage("scheduler integration", "tests/integration", "scheduler")
        return [stage] if stage else []
    return [*BACKEND, *FRONTEND_STAGES]


def run_stage(stage: Stage) -> bool:
    run_options: dict[str, object] = {
        "cwd": stage.cwd,
        "check": False,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if stage.capture_output:
        run_options["capture_output"] = True
    completed = subprocess.run(stage.command, **run_options)
    if completed.returncode == 0:
        print(f"PASS  {stage.name}")
        return True

    print(f"FAIL  {stage.name}")
    details = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
    )
    if details:
        print(details)
    return False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ShotMill verification stages.")
    parser.add_argument(
        "--area",
        choices=("backend", "frontend", "providers", "scheduler", "e2e", "ui"),
        help="Run the smallest relevant verification area.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all available verification stages.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv or sys.argv[1:])
    selected = stages_for(args.area or "default", args.full)
    if not selected:
        print(f"PASS  {args.area}: no matching tests yet")
        return 0

    for stage in selected:
        if not run_stage(stage):
            return 1
    print(f"PASS  verification ({len(selected)} stages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

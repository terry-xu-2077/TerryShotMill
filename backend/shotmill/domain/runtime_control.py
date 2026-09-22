from dataclasses import dataclass


@dataclass
class RuntimeControl:
    job_id: str
    paused: bool = False
    hidden: bool = False
    position: float | None = None

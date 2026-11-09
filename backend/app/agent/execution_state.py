from dataclasses import dataclass, field, asdict


@dataclass
class ExecutionState:
    status: str = 'pending'
    trace: list[dict] = field(default_factory=list)
    failed_step: str | None = None

    def to_dict(self):
        return asdict(self)

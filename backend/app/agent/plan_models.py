from dataclasses import dataclass, field, asdict


@dataclass
class PlanStep:
    id: str
    tool: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)
    inputs_from: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    plan_id: str
    question: str
    route: str
    steps: list[PlanStep]

    def to_dict(self) -> dict:
        return asdict(self)

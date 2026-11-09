from dataclasses import dataclass, field
from app.agent.models import ToolResult


@dataclass
class ExecutionContext:
    question: str
    plan_id: str
    variables: dict = field(default_factory=dict)
    step_results: dict[str, ToolResult] = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)

from dataclasses import dataclass, field, asdict


@dataclass
class ToolResult:
    tool: str
    success: bool
    data: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    error: dict | None = None
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

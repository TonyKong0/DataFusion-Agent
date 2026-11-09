from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_type: str
    source_name: str
    content: object
    provenance: dict
    confidence: float
    step_id: str
    tool: str

    def to_dict(self):
        return asdict(self)

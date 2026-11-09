from dataclasses import dataclass, asdict


@dataclass
class QualityIssue:
    page: int
    type: str
    severity: str
    message: str
    evidence: dict

    def to_dict(self):
        return asdict(self)

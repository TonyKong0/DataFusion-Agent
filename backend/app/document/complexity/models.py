from dataclasses import dataclass, asdict


@dataclass
class ComplexityResult:
    score: int
    level: str
    factors: list[str]
    recommended_strategy: list[str]
    features: dict

    def to_dict(self):
        return asdict(self)

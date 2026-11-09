from dataclasses import dataclass, field, asdict


@dataclass
class FormulaCandidate:
    formula_id: str
    page: int
    raw_text: str
    variables: list[str]
    heading_path: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class FormulaParameter:
    name: str
    raw_value: str
    normalized_value: float
    unit: str
    page: int
    source_text: str
    confidence: float
    candidates: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

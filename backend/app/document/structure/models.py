from dataclasses import dataclass, asdict


@dataclass
class Heading:
    title: str
    level: int
    page: int
    parent: str | None
    confidence: float

    def to_dict(self):
        return asdict(self)

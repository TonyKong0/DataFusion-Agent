"""Shared input structure for future semantic processing phases."""

from dataclasses import asdict, dataclass
from typing import Any

from app.semantic.config_loader import load_config


@dataclass(frozen=True, slots=True)
class SemanticRequest:
    original_question: str


@dataclass(frozen=True, slots=True)
class Element:
    type: str
    canonical_value: Any
    source: str
    confidence: float
    name: str | None = None
    raw_value: str | None = None

    def __post_init__(self) -> None:
        if self.type not in load_config('element_types.yaml')['elements']:
            raise ValueError(f'Unknown element type: {self.type}')
        if not 0 <= self.confidence <= 1:
            raise ValueError('confidence must be between 0 and 1')
        if self.source not in {'dictionary', 'rule', 'llm'}:
            raise ValueError(f'Unknown element source: {self.source}')

    def to_dict(self) -> dict:
        return asdict(self)

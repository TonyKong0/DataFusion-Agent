from dataclasses import dataclass, field, asdict


@dataclass
class DocumentPage:
    document_id: str
    page: int
    text: str
    blocks: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    formulas: list[dict] = field(default_factory=list)
    headings: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentNode:
    title: str
    level: int
    page: int
    kind: str = 'section'
    children: list['DocumentNode'] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentTree:
    document_id: str
    children: list[DocumentNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

"""A directed, database-declared foreign-key relationship."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    constraint_name: str

    def reversed(self) -> 'Relationship':
        return Relationship(self.to_table, self.to_column, self.from_table,
                            self.from_column, self.constraint_name)

    def to_dict(self) -> dict:
        return {'from_table': self.from_table, 'from_column': self.from_column,
                'to_table': self.to_table, 'to_column': self.to_column,
                'constraint_name': self.constraint_name}


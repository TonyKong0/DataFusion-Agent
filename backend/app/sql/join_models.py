from dataclasses import dataclass


@dataclass(frozen=True)
class JoinEdge:
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    constraint_name: str

    def to_dict(self) -> dict:
        return {'left_table': self.left_table, 'left_column': self.left_column,
                'right_table': self.right_table, 'right_column': self.right_column,
                'constraint_name': self.constraint_name}


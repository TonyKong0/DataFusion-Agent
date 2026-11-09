"""Read-only graph built solely from declared foreign keys."""

from collections import deque

from app.schema.models import SchemaMetadata
from app.schema.relationship import Relationship


class SchemaGraph:
    def __init__(self, metadata: SchemaMetadata):
        self.tables = {table.table_name.lower(): table.table_name for table in metadata.tables}
        self.edges: dict[str, list[Relationship]] = {name: [] for name in self.tables}
        columns = {table.table_name.lower(): {col.name.lower() for col in table.columns}
                   for table in metadata.tables}
        for table in metadata.tables:
            for key in table.foreign_keys:
                target = key.references_table.lower()
                source = table.table_name.lower()
                if target not in self.tables or key.column.lower() not in columns[source] or (
                        key.references_column.lower() not in columns[target]):
                    continue
                edge = Relationship(table.table_name, key.column, self.tables[target],
                                    key.references_column, key.constraint_name)
                self.edges[source].append(edge)
                self.edges[target].append(edge.reversed())
        for group in self.edges.values():
            group.sort(key=lambda edge: (edge.to_table.lower(), edge.constraint_name, edge.from_column))

    def neighbors(self, table: str) -> list[str]:
        key = table.lower()
        if key not in self.tables:
            raise ValueError(f'Unknown table: {table}')
        return list(dict.fromkeys(edge.to_table for edge in self.edges[key]))

    def shortest_path(self, start: str, end: str) -> list[Relationship]:
        source, target = start.lower(), end.lower()
        if source not in self.tables or target not in self.tables:
            raise ValueError('Unknown table')
        if source == target:
            return []
        queue = deque([(source, [])])
        seen = {source}
        while queue:
            current, path = queue.popleft()
            for edge in self.edges[current]:
                following = edge.to_table.lower()
                if following in seen:
                    continue
                next_path = [*path, edge]
                if following == target:
                    return next_path
                seen.add(following)
                queue.append((following, next_path))
        raise ValueError(f'No foreign-key path: {start} -> {end}')

    def is_real_edge(self, edge: Relationship) -> bool:
        return edge.from_table.lower() in self.edges and edge in self.edges[edge.from_table.lower()]

    def validate_path(self, start: str, end: str, path: list[Relationship]) -> bool:
        current = start.lower()
        for edge in path:
            if edge.from_table.lower() != current or not self.is_real_edge(edge):
                return False
            current = edge.to_table.lower()
        return current == end.lower()


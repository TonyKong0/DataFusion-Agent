"""Connect selected tables using only shortest paths in the live FK graph."""

from app.core.errors import AppError
from app.schema.schema_graph import SchemaGraph
from app.sql.join_models import JoinEdge


def plan_join_path(selected_tables: list[str], graph: SchemaGraph) -> dict:
    if not selected_tables:
        raise AppError('JOIN_PATH_NOT_FOUND', '没有可关联的数据表', 422)
    requested = list(dict.fromkeys(table.lower() for table in selected_tables))
    if any(table not in graph.tables for table in requested):
        raise AppError('JOIN_PATH_NOT_FOUND', '选定表不在当前数据库结构中', 422)
    connected = {requested[0]}
    ordered = [graph.tables[requested[0]]]
    edges: list[JoinEdge] = []
    pending = set(requested[1:])
    while pending:
        options = []
        for start in sorted(connected):
            for target in sorted(pending):
                try:
                    path = graph.shortest_path(start, target)
                    options.append((len(path), start, target, path))
                except ValueError:
                    continue
        if not options:
            raise AppError('JOIN_PATH_NOT_FOUND', '选定表之间没有真实外键路径', 422)
        _, _, _, path = min(options, key=lambda item: item[:3])
        for relation in path:
            destination = relation.to_table.lower()
            if destination not in connected:
                edges.append(JoinEdge(relation.from_table, relation.from_column,
                                      relation.to_table, relation.to_column, relation.constraint_name))
                connected.add(destination)
                ordered.append(relation.to_table)
                pending.discard(destination)
    return {'join_tables': ordered, 'join_path': [edge.to_dict() for edge in edges],
            'selected_tables': [graph.tables[table] for table in requested]}

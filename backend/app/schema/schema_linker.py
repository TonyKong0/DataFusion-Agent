"""Select real, coherent tables/columns from recalled schema candidates."""

from app.schema.models import SchemaMetadata
from app.schema.schema_graph import SchemaGraph


def link_schema(question: str, elements: list[dict], candidates: dict,
                metadata: SchemaMetadata) -> dict:
    graph = SchemaGraph(metadata)
    real_tables = {table.table_name.lower(): table for table in metadata.tables}
    real_columns = {(table.table_name.lower(), col.name.lower()): col.name
                    for table in metadata.tables for col in table.columns}

    candidate_tables = {item['table'].lower(): item for item in candidates.get('candidate_tables', [])
                        if item.get('table', '').lower() in real_tables}
    candidate_columns = {(item['table'].lower(), item['column'].lower()): item
                         for item in candidates.get('candidate_columns', [])
                         if (item.get('table', '').lower(), item.get('column', '').lower()) in real_columns}
    explicit = {key for key, item in candidate_tables.items() if item['score'] >= 0.90
                and any(reason.startswith(('table_alias:', 'table_name', 'semantic_entity'))
                        for reason in item.get('reasons', []))}
    selected = set(explicit)
    cross_table_cue = any(term in question for term in (
        '消费', '花费', '卖出', '卖得', '销量', '销售数量', '销售量', '购买歌曲', '购买曲目'))
    if explicit and cross_table_cue:
        changed = True
        while changed:
            changed = False
            for (table, _), item in candidate_columns.items():
                if item['score'] < 0.78 or table in selected or not any(
                        reason.startswith('business_keyword:') for reason in item.get('reasons', [])):
                    continue
                if any(table in {neighbor.lower() for neighbor in graph.neighbors(anchor)} for anchor in selected):
                    selected.add(table)
                    changed = True
    if not selected and candidate_tables:
        selected.add(max(candidate_tables, key=lambda key: candidate_tables[key]['score']))

    ordered = sorted(selected, key=lambda key: (-candidate_tables.get(key, {}).get('score', 0), key))
    columns = []
    for table in ordered:
        for (candidate_table, column), item in candidate_columns.items():
            if candidate_table == table and item['score'] >= 0.65:
                columns.append(f'{real_tables[table].table_name}.{real_columns[(table, column)]}')
        for col in real_tables[table].columns:
            if col.primary_key:
                columns.append(f'{real_tables[table].table_name}.{col.name}')
        display_fields = {'customer': ('FirstName', 'LastName'), 'employee': ('FirstName', 'LastName'),
                          'artist': ('Name',), 'album': ('Title',), 'genre': ('Name',),
                          'track': ('Name',), 'playlist': ('Name',), 'mediatype': ('Name',)}
        for name in display_fields.get(table, ()):
            key = (table, name.lower())
            if key in real_columns:
                columns.append(f'{real_tables[table].table_name}.{real_columns[key]}')
    columns = list(dict.fromkeys(columns))
    confidence = round(min((candidate_tables.get(key, {}).get('score', 0.6) for key in ordered),
                           default=0.0), 3)
    return {'selected_tables': [real_tables[key].table_name for key in ordered],
            'selected_columns': columns, 'confidence': confidence,
            'needs_clarification': not ordered or confidence < 0.6,
            'method': 'rules+fk_coherence'}

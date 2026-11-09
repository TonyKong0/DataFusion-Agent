from uuid import uuid4
import sqlglot
from sqlglot import exp
from app.evidence.models import Evidence
from app.evidence.validator import validate_evidence


def _tables(sql: str) -> list[str]:
    expression = sqlglot.parse_one(sql, read='mysql')
    return list(dict.fromkeys(table.name for table in expression.find_all(exp.Table)))


def from_tool_result(result, step_id: str, document_name: str | None = None) -> list[dict]:
    if not result.success:
        return []
    data, tool = result.data, result.tool
    items = []
    if tool == 'database_query' and data.get('sql'):
        sql = data['sql']
        content = {'columns': data.get('columns', []), 'rows': data.get('rows', []),
                   'row_count': data.get('row_count', len(data.get('rows', [])))}
        items.append(Evidence('ev_' + uuid4().hex, 'database', 'Chinook', content,
                              {'sql': sql, 'tables': _tables(sql)}, 1.0, step_id, tool).to_dict())
    elif tool == 'document_search':
        for source in data.get('sources') or []:
            source_document_id = source.get('document_id') or data.get('document_id')
            provenance = {'document_id': source_document_id, 'page': source.get('page'),
                          'heading_path': source.get('heading_path', []), 'chunk_id': source.get('chunk_id'),
                          'locator': source.get('locator'), 'kind': source.get('kind'),
                          'extension': source.get('extension'),
                          'preview_available': source.get('preview_available'),
                          'text': source.get('text')}
            name = source.get('filename') or document_name or source_document_id or '材料'
            items.append(Evidence('ev_' + uuid4().hex, 'document', name,
                                  source.get('text', ''), provenance, float(source.get('score') or 0.8),
                                  step_id, tool).to_dict())
    elif tool == 'formula_calculate':
        source = data.get('source') or {}
        provenance = {'document_id': source.get('document_id'), 'page': source.get('page'),
                      'heading_path': source.get('heading_path', []), 'chunk_id': source.get('chunk_id'),
                      'text': source.get('text'), 'expression': data.get('expression'),
                      'parameters': data.get('parameters'), 'parameter_source': data.get('parameter_source'),
                      'database_sql': data.get('database_sql')}
        items.append(Evidence('ev_' + uuid4().hex, 'formula', document_name or source.get('document_id', 'PDF'),
                              data.get('result'), provenance, 1.0, step_id, tool).to_dict())
    elif tool == 'multi_document_search':
        for source in data.get('sources') or []:
            provenance = {'document_id': source['document_id'], 'document_version': source.get('document_version'),
                          'page': source['page'], 'heading_path': source.get('heading_path', []),
                          'chunk_id': source['chunk_id'], 'text': source['text'],
                          'locator': source.get('locator'), 'extension': source.get('extension'),
                          'preview_available': source.get('preview_available'),
                          'cross_document_rank': source.get('cross_document_rank')}
            items.append(Evidence('ev_' + uuid4().hex, 'text', source['filename'], source['text'],
                                  provenance, float(source.get('score') or 0), step_id, tool).to_dict())
    elif tool == 'document_compare':
        for change in data.get('changes') or []:
            provenance = {'old_source': change.get('old_source'), 'new_source': change.get('new_source'),
                          'document_id': (change.get('new_source') or change.get('old_source') or {}).get('document_id'),
                          'page': (change.get('new_source') or change.get('old_source') or {}).get('page'),
                          'text': '\n'.join(filter(None, (change.get('old'), change.get('new'))))}
            items.append(Evidence('ev_' + uuid4().hex, 'version_diff', change['section'],
                                  {'change_type': change['change_type'], 'old': change['old'], 'new': change['new']},
                                  provenance, 1.0, step_id, tool).to_dict())
    elif tool in ('table_query', 'chart_analyze', 'image_query'):
        kind = {'table_query': 'table', 'chart_analyze': 'chart', 'image_query': 'image'}[tool]
        for source in data.get('sources') or []:
            original = (' | '.join(map(str, source.get('row', []))) if kind == 'table' else
                        source.get('source_text', '') if kind == 'chart' else
                        ' | '.join(item['text'] for item in source.get('ocr_labels', [])))
            provenance = {'document_id': source['document_id'], 'page': source['page'],
                          'text': original, 'heading_path': source.get('heading_path', []),
                          'locator': source.get('locator') or ({'sheet': source.get('sheet')}
                              if source.get('sheet') else None), 'kind': source.get('kind'),
                          'extension': source.get('extension'),
                          'preview_available': source.get('preview_available'),
                          'row_index': source.get('row_index'), 'column_index': source.get('column_index'),
                          'image_index': source.get('image_index'), 'table_index': source.get('table_index'),
                          'chart_index': source.get('chart_index')}
            items.append(Evidence('ev_' + uuid4().hex, kind, source.get('filename', 'PDF'),
                                  source, provenance, float(source.get('confidence') or 1), step_id, tool).to_dict())
    return [validate_evidence(item) for item in items]

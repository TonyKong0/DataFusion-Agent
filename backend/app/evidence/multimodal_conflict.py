"""Compare explicit metric values only; never infer a metric from arbitrary numbers."""
import re

METRICS = ('增长率', '销售额', '销量', '审核阈值', '金额上限')


def _facts(item: dict) -> list[tuple[str, str]]:
    if item.get('fact_key') and item.get('fact_value') is not None:
        return [(str(item['fact_key']), str(item['fact_value']).strip())]
    kind, content = item.get('source_type'), item.get('content')
    if kind in ('text', 'document') and isinstance(content, str):
        return [(metric, match.group(1)) for metric in METRICS
                if (match := re.search(re.escape(metric) + r'\s*(?:为|是|[:：])?\s*(-?\d+(?:\.\d+)?%?)', content))]
    if kind == 'table' and isinstance(content, dict):
        column = content.get('column_index')
        headers, row = content.get('headers') or [], content.get('row') or []
        if isinstance(column, int) and 0 <= column < min(len(headers), len(row)):
            return [(headers[column], str(row[column]).strip())]
    if kind == 'chart' and isinstance(content, dict):
        if content.get('legend') and len(content.get('series') or []) == 1:
            return [(content['legend'], str(content['series'][0]['value']))]
    if kind == 'database' and isinstance(content, dict):
        columns, rows = content.get('columns') or [], content.get('rows') or []
        if len(columns) == 1 and len(rows) == 1 and len(rows[0]) == 1:
            return [(columns[0], str(rows[0][0]))]
    return []


def detect_multimodal_conflicts(evidence: list[dict]) -> list[dict]:
    groups = {}
    for item in evidence:
        for topic, value in _facts(item):
            if value:
                groups.setdefault(topic, []).append({'source': item['source_type'],
                    'source_name': item['source_name'], 'value': value,
                    'evidence_id': item['evidence_id'], 'provenance': item.get('provenance', {})})
    conflicts = []
    for topic, values in groups.items():
        normalized = {value['value'].replace('%', '').strip().casefold() for value in values}
        if len(values) >= 2 and len(normalized) > 1:
            conflicts.append({'topic': topic, 'conflict': True, 'values': values,
                              'evidence_ids': [value['evidence_id'] for value in values],
                              'resolution': 'unresolved'})
    return conflicts

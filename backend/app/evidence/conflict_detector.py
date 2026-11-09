import re


def _value(item: dict):
    if 'fact_value' in item:
        return item['fact_value']
    content = item.get('content')
    if isinstance(content, dict):
        rows = content.get('rows') or []
        if len(rows) == 1 and len(rows[0]) == 1:
            return rows[0][0]
    if isinstance(content, (int, float)):
        return content
    if isinstance(content, str):
        matches = re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', content)
        if len(matches) == 1:
            return float(matches[0])
    return None


def detect_conflicts(evidence: list[dict]) -> list[dict]:
    groups = {}
    for item in evidence:
        key = item.get('fact_key')
        value = _value(item)
        if key and value is not None:
            groups.setdefault(key, []).append((item, value))
    conflicts = []
    for key, entries in groups.items():
        if len({str(value).strip().lower() for _, value in entries}) > 1:
            conflicts.append({'topic': key, 'evidence_ids': [item['evidence_id'] for item, _ in entries],
                              'values': [value for _, value in entries], 'resolution': 'unresolved'})
    return conflicts

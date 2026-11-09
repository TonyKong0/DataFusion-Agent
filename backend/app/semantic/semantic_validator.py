"""Fail closed before SQL generation when a question is not unambiguous."""

from app.semantic.config_loader import load_config


def validate_semantics(question: str, extraction: dict, confirmed: bool = False) -> dict:
    rules = load_config('semantic_rules.yaml')['rules']
    elements = extraction['elements']
    entities = [item.canonical_value for item in elements if item.type == 'entity']
    missing = []
    ambiguities = []
    unsupported = []
    if rules['require_entity'] and not entities:
        missing.append('entity')
    if len(set(entities)) > 1:
        ambiguities.append('entity')
    if any(term in question for term in rules['require_time_for']) and not any(item.type == 'time' for item in elements):
        missing.append('time_range')
    if len(set(entities)) > 1 or any(term in question for term in ('关联', '连接', 'JOIN')):
        unsupported.append('multi_table')
    if len(set(entities)) == 1:
        entity = entities[0]
        if entity != 'Invoice' and any(term in question for term in rules['require_time_for']):
            unsupported.append('metric:growth_rate')
        allowed_filters = rules['single_table_filters'].get(entity, [])
        for item in elements:
            if item.type == 'filter' and item.name not in allowed_filters:
                unsupported.append(f'filter:{item.name}')
            if item.type == 'sort' and item.name == 'price' and entity not in rules['price_sort_entities']:
                unsupported.append('sort:price')
            if item.type == 'metric' and item.canonical_value == 'sales':
                unsupported.append('metric:sales')
    low_confidence = any(item.confidence < rules['min_confidence'] for item in elements) and not confirmed
    conflicts = extraction.get('conflicts', [])
    error = extraction.get('error')
    need_clarification = bool(missing or ambiguities or unsupported or low_confidence or conflicts or error)
    return {'valid': not need_clarification, 'need_clarification': need_clarification,
            'missing': missing, 'ambiguities': ambiguities, 'unsupported': list(dict.fromkeys(unsupported)),
            'low_confidence': low_confidence, 'conflicts': conflicts, 'error': error}

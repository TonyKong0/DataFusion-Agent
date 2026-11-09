def evidence_lineage(item: dict) -> dict:
    return {'evidence_id': item['evidence_id'], 'tool': item['tool'],
            'step_id': item['step_id'], 'source': item['source_name'],
            'provenance': item['provenance']}

from app.evidence.conflict_detector import _value, detect_conflicts


def fuse_evidence(evidence: list[dict], required_sources: list[str] | None = None,
                  execution_complete: bool = True) -> dict:
    required = set(required_sources or [])
    present = {item['source_type'] for item in evidence}
    missing = [f'缺少{source}证据' for source in sorted(required - present)]
    if not execution_complete:
        missing.append('执行计划未完成')
    conflicts = detect_conflicts(evidence)
    facts = [{'evidence_id': item['evidence_id'], 'source_type': item['source_type'],
              'fact_key': item.get('fact_key'), 'value': _value(item), 'content': item['content']}
             for item in evidence]
    return {'facts': facts, 'conflicts': conflicts, 'missing': missing,
            'sufficient': not missing and not conflicts}

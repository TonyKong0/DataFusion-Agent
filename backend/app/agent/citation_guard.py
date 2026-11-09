from app.evidence.validator import validate_evidence


def guard_claims(claims: list[dict], evidence: list[dict]) -> tuple[list[dict], list[str]]:
    valid = {}
    for item in evidence:
        try:
            validate_evidence(item)
            valid[item['evidence_id']] = item
        except (KeyError, ValueError, TypeError):
            continue
        except Exception:
            continue
    accepted, warnings = [], []
    for claim in claims:
        ids = claim.get('evidence_ids') or []
        if claim.get('text') and ids and all(item in valid for item in ids):
            accepted.append(claim)
        else:
            warnings.append('已移除无有效证据的结论')
    return accepted, warnings

def combined_confidence(evidence: list[dict]) -> float:
    if not evidence:
        return 0.0
    return round(min(float(item.get('confidence', 0)) for item in evidence), 3)

"""Keep user input separate from the text interpreted by downstream tools."""


def preserve_question(result: dict, original: str, interpreted: str) -> dict:
    result = {**result, 'original_question': original, 'resolved_question': interpreted}
    semantic = result.get('semantic')
    if isinstance(semantic, dict):
        changes = list(semantic.get('changes') or [])
        if original != interpreted:
            change = {'type': 'context', 'from': original, 'to': interpreted}
            if change not in changes:
                changes.insert(0, change)
        result['semantic'] = {**semantic, 'original_question': original,
                              'interpreted_question': interpreted, 'changes': changes}
    return result

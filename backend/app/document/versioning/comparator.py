import difflib
import re
from app.core.errors import AppError
from app.services.document_service import load_document


def _sections(document: dict) -> list[dict]:
    grouped = {}
    for chunk in document.get('content', []):
        path = tuple(chunk.get('heading_path') or [])
        key = path or (f"第 {chunk['page']} 页",)
        row = grouped.setdefault(key, {'section': ' / '.join(key), 'heading_path': list(path),
                                       'page': chunk['page'], 'parts': [], 'chunk_ids': []})
        row['parts'].append(chunk['text'].strip())
        row['chunk_ids'].append(chunk['chunk_id'])
    return [{**row, 'text': '\n'.join(row.pop('parts'))} for row in grouped.values()]


def compare(old_id: str, new_id: str) -> dict:
    if old_id == new_id:
        raise AppError('INVALID_VERSION_PAIR', '请选择两份不同的 PDF', 422)
    old, new = load_document(old_id), load_document(new_id)
    before, after = _sections(old), _sections(new)
    matches, used = {}, set()
    for i, section in enumerate(before):
        candidates = [(difflib.SequenceMatcher(None, section['section'], target['section']).ratio(), j)
                      for j, target in enumerate(after) if j not in used]
        if candidates:
            score, j = max(candidates)
            if score >= .8:
                matches[i] = j
                used.add(j)
    changes = []

    def source(document, section):
        extension = document.get('extension') or document.get('filename', '').rsplit('.', 1)[-1].lower()
        return {'document_id': document['document_id'], 'filename': document['filename'],
                'extension': extension, 'preview_available': bool(document.get('preview_available')),
                'page': section['page'], 'heading_path': section['heading_path'],
                'chunk_ids': section['chunk_ids'], 'text': section['text']}

    for i, section in enumerate(before):
        target = after[matches[i]] if i in matches else None
        if target and section['text'] == target['text'] and section['section'] == target['section']:
            continue
        old_text, new_text = section['text'], target['text'] if target else ''
        numbers_old = re.findall(r'\d+(?:\.\d+)?%?', old_text)
        numbers_new = re.findall(r'\d+(?:\.\d+)?%?', new_text)
        changes.append({'section': target['section'] if target else section['section'],
                        'change_type': 'modified' if target else 'deleted',
                        'change_details': ([name for flag, name in (
                            (numbers_old != numbers_new, 'numeric_change'),
                            (section['section'] != target['section'] if target else False, 'heading_change'),
                            (bool(re.search(r'[=＝]', old_text)) != bool(re.search(r'[=＝]', new_text)), 'formula_change')) if flag]
                            if target else []),
                        'old': old_text, 'new': new_text,
                        'old_source': source(old, section), 'new_source': source(new, target) if target else None})
    for j, section in enumerate(after):
        if j not in used:
            changes.append({'section': section['section'], 'change_type': 'added', 'change_details': [],
                            'old': '', 'new': section['text'], 'old_source': None,
                            'new_source': source(new, section)})
    counts = {kind: sum(item['change_type'] == kind for item in changes)
              for kind in ('added', 'deleted', 'modified')}
    return {'success': True, 'old_document_id': old_id, 'new_document_id': new_id,
            'changes': changes, 'summary': f"新增 {counts['added']} 节，删除 {counts['deleted']} 节，修改 {counts['modified']} 节。",
            'counts': counts}

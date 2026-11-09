"""High-confidence facts derived from the selected document's own text."""

import json
import re
from collections.abc import Callable

from app.core.errors import AppError

AUTHOR_QUESTION = re.compile(
    r'作者.{0,8}(?:谁|哪位|叫什么|什么名字)|(?:谁|哪位).{0,8}(?:写|创作|撰写)')
CHINESE_NAME = re.compile(r'^[\u4e00-\u9fff]{2,4}$')
SECTION_LABEL = re.compile(r'第[一二三四五六七八九十\d]|课|章|节|目录|目标|内容|背景|导入|赏析|阅读')
BIOGRAPHY_NAME = re.compile(
    r'(?:^|\n)\s*[【\[]?([\u4e00-\u9fff]{2,4})[】\]]?\s*[（(](?:公元)?\d{3,4}', re.MULTILINE)
AUTHOR_EXTRACT_SYSTEM = '''只从给定的每份材料片段中找该材料所指作品的作者，不使用常识或其他文件的作者。
逐份判断；材料中的“作者简介”、题目页或作品与姓名的明确署名可以作为依据。
人物只是被提及、引述或出现在无关作品旁边时不能认定为作者。找不到时不要输出该材料。
只返回 JSON：{"authors":[{"document_id":"","author":"","chunk_id":""}]}。'''


def _titles(document: dict) -> list[str]:
    stem = document.get('filename', '').rsplit('.', 1)[0]
    titles = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9 -]{3,}', stem)
    content = document.get('content') or []
    if content:
        first_page = min(chunk.get('page', 1) for chunk in content)
        for chunk in content:
            if chunk.get('page', 1) != first_page:
                continue
            for line in chunk.get('text', '').splitlines():
                title = line.strip(' 《》〈〉-—:：·\t')
                if 2 <= len(title) <= 30 and not re.search(r'模板|WWW\.|www\.', title):
                    titles.append(title)
    return list(dict.fromkeys(titles))


def title_matches_question(document: dict, question: str) -> bool:
    title = _display_title(document)
    generic = {'文章', '文档', '材料', '资料', '报告', '课件'}
    if len(title) >= 2 and title not in generic and title.lower() in question.lower():
        return True
    # Uploaded file names need not be the work title. Use source-confirmed cover
    # signatures and top-level headings rather than a predefined work dictionary.
    found = _author_evidence(document)
    source_title = found[2] if found else None
    if source_title and source_title not in generic and source_title.casefold() in question.casefold():
        return True
    for heading in (document.get('processing') or {}).get('headings', []):
        candidate = str(heading.get('title') or '').strip(' 《》')
        if (heading.get('level') == 1 and len(candidate) >= 2
                and candidate not in generic and not SECTION_LABEL.search(candidate)
                and candidate.casefold() in question.casefold()):
            return True
    return False


def _display_title(document: dict, evidence_title: str | None = None) -> str:
    stem = document.get('filename', '').rsplit('.', 1)[0]
    stem = re.sub(r'^\d+[+_. -]*', '', stem)
    stem = re.sub(r'\s*[（(]\d+[)）]\s*[-_]*$', '', stem)
    stem = re.sub(r'(?:教学)?课件$', '', stem).strip(' _-')
    if len(stem) >= 2 and re.search(r'[\u4e00-\u9fff]', stem):
        return stem
    return evidence_title or next((title for title in _titles(document)
                                   if re.search(r'[\u4e00-\u9fff]{2,}', title)
                                   and not re.search(r'作者|简介|背景|课件|模板', title)),
                                  document.get('filename', '材料'))


def _author_evidence(document: dict) -> tuple[str, dict, str | None] | None:
    content = document.get('content') or []
    titles = _titles(document)
    likely_titles = list(dict.fromkeys([_display_title(document), *titles]))
    likely_titles = [title for title in likely_titles if not re.search(
        r'作者|简介|背景|课件|模板|目录|导入', title)]
    known_names = set()
    relation_candidates = []
    for chunk in content:
        known_names.update(BIOGRAPHY_NAME.findall(chunk.get('text') or ''))
    for chunk in content:
        text = chunk.get('text') or ''
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines[:-1]):
            if (line.strip('《》〈〉') in likely_titles and CHINESE_NAME.fullmatch(lines[index + 1])
                    and not SECTION_LABEL.search(lines[index + 1])):
                return lines[index + 1], chunk, line.strip('《》〈〉')
        explicit = re.search(r'作者\s*[:：]\s*([\u4e00-\u9fff]{2,4})', text)
        if explicit:
            return explicit.group(1), chunk, None
        for title in likely_titles:
            for name in known_names:
                if re.search(re.escape(name) + r'(?:的|写(?:的|下|了)?|创作(?:的|了)?|撰写(?:的|了)?|著)'
                             r'[^。！？\n《》]{0,24}《' + re.escape(title) + r'》', text):
                    relation_candidates.append((name, chunk, title))
    if len({name for name, _, _ in relation_candidates}) == 1:
        return relation_candidates[0]
    return None


def _model_author_evidence(documents: list[dict], chat_json: Callable) -> dict[str, tuple[str, dict]]:
    """One bounded extraction call for unresolved materials; only cited text can support a name."""
    candidates = {}
    payload = []
    for document in documents:
        chunks = document.get('content') or []
        titles = _titles(document)
        opening = sorted(chunks, key=lambda chunk: chunk.get('page', 0))[:2]
        relevant = sorted(chunks, key=lambda chunk: (
            -int(bool(re.search(r'作者|撰写|创作|编著|署名|\bby\b', chunk.get('text', ''), re.I))),
            -int(any(title in chunk.get('text', '') for title in titles)),
            chunk.get('page', 0)))[:5]
        ranked = list({chunk['chunk_id']: chunk for chunk in [*opening, *relevant]}.values())[:6]
        candidates[document['document_id']] = {chunk['chunk_id']: chunk for chunk in ranked}
        payload.append({'document_id': document['document_id'], 'filename': document['filename'],
                        'chunks': [{'chunk_id': chunk['chunk_id'], 'page': chunk.get('page'),
                                    'text': chunk.get('text', '')[:700]} for chunk in ranked]})
    if not payload:
        return {}
    try:
        output = chat_json(AUTHOR_EXTRACT_SYSTEM, json.dumps({'documents': payload}, ensure_ascii=False))
    except AppError:
        return {}
    if not isinstance(output, dict):
        return {}
    found = {}
    for item in output.get('authors', []) if isinstance(output.get('authors'), list) else []:
        if not isinstance(item, dict):
            continue
        identifier, name, chunk_id = item.get('document_id'), item.get('author'), item.get('chunk_id')
        source = candidates.get(identifier, {}).get(chunk_id)
        if (isinstance(name, str) and name.strip() and len(name.strip()) <= 40
                and source and name.strip() in source.get('text', '')):
            found[identifier] = (name.strip(), source)
    return found


def author_answer(documents: list[dict], question: str,
                  chat_json: Callable | None = None) -> dict | None:
    if not AUTHOR_QUESTION.search(question):
        return None
    documents = [{**document, 'document_id': document.get('document_id') or f'selected_{index}'}
                 for index, document in enumerate(documents)]
    matched = [document for document in documents if title_matches_question(document, question)]
    targets = matched or documents
    if not targets:
        return None
    found_by_id = {document['document_id']: found for document in targets
                   if (found := _author_evidence(document))}
    unresolved = [document for document in targets if document['document_id'] not in found_by_id]
    if unresolved and chat_json:
        for identifier, (name, chunk) in _model_author_evidence(unresolved, chat_json).items():
            found_by_id[identifier] = (name, chunk, None)
    answers, sources = [], []
    for document in targets:
        found = found_by_id.get(document['document_id'])
        if not found:
            answers.append(f'《{_display_title(document)}》：当前材料中未找到可确认的作者依据。')
            continue
        author, chunk, evidence_title = found
        title = next((item for item in _titles(document) if item in question), None)
        title = title or _display_title(document, evidence_title)
        answers.append(f'《{title}》的作者是{author}。')
        sources.append({**chunk, 'document_id': document['document_id'],
                        'filename': document.get('filename', '材料'), 'score': 1.0})
    if not sources:
        return None
    return {'success': True, 'question': question, 'answer': '\n'.join(answers),
            'sources': sources, 'document_ids': [doc['document_id'] for doc in documents],
            'trace': [{'step': 'author_evidence', 'name': 'author_evidence', 'status': 'success'}]}

import hashlib
import json
import re
from time import perf_counter

from app.core.errors import AppError
from app.services.document_service import load_document
from app.services.vector_store import ready
from app.services.rag_service import AUTHOR_PATTERN, ORIGINAL_PATTERN, OVERVIEW_PATTERN, retrieve_hits, retrieve_original_hits
from app.llm.deepseek_client import chat_json
from app.services.rag_answer import generate as generate_answer, normalize_citations, is_unknown_answer
from app.llm.prompts import RAG_SYSTEM
from app.services.document_facts import title_matches_question as _title_matches_question


def _version(filename: str) -> str | None:
    match = re.search(r'(?i)(?:^|[_\s-])(v\d+|20\d{2})(?:[_\s.-]|$)', filename)
    return match.group(1) if match else None


COMPARISON_PATTERN = re.compile(r'比较|对比|异同|区别|不同|相同|差异|共同点')


def _coverage_question(question: str) -> bool:
    if COMPARISON_PATTERN.search(question) or AUTHOR_PATTERN.search(question):
        return True
    return bool(OVERVIEW_PATTERN.search(question) and re.search(
        r'这(?:[一二两三四五六七八九十\d]+|几|些)(?:篇|份|个)|这些|所选|选中|每篇|各篇|每份|各份|文档.{0,4}(?:讲|主要内容)',
        question))


def retrieve_many(document_ids: list[str], question: str, top_k: int = 6) -> list[dict]:
    ids = list(dict.fromkeys(document_ids))
    if not 2 <= len(ids) <= 10:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '请选择 2–10 份不同的材料', 422)
    if not question.strip():
        raise AppError('INVALID_QUESTION', '问题不能为空', 422)
    candidates = []
    per_document_hits = []
    original_request = bool(ORIGINAL_PATTERN.search(question))
    coverage = _coverage_question(question)
    per_doc = max(2, min(8 if original_request else 5, top_k))
    documents = []
    for document_id in ids:
        document = load_document(document_id)
        if document.get('status') != 'indexed' or not ready(document_id):
            raise AppError('INDEX_NOT_READY', f'{document.get("filename", document_id)} 尚未建立索引', 409)
        documents.append(document)
    targets = {document['document_id'] for document in documents
               if _title_matches_question(document, question)}
    for document in documents:
        if targets and document['document_id'] not in targets:
            continue
        document_id = document['document_id']
        # Preserve the requested attribute instead of replacing it with an overview.
        hits = (retrieve_original_hits(document, question, per_doc) if original_request else
                retrieve_hits(document, question, per_doc))
        document_hits = []
        for hit in hits:
            document_hits.append({**hit, 'document_id': document_id,
                               'extension': document.get('extension') or
                                   document.get('filename', '').rsplit('.', 1)[-1].lower(),
                               'preview_available': bool(document.get('preview_available')),
                               'document_version': _version(document.get('filename', '')),
                               'filename': document['filename'], 'source_weight': 1.0,
                               'cross_document_score': float(hit.get('retrieval_score', hit.get('score')) or 0)})
        per_document_hits.append(document_hits)
        candidates.extend(document_hits)
    if coverage or original_request:
        candidates = [group[index] for index in range(max(map(len, per_document_hits), default=0))
                      for group in per_document_hits if index < len(group)]
    else:
        candidates.sort(key=lambda item: (-item['cross_document_score'], item['document_id'], item['chunk_id']))
    seen, ranked = {}, []
    for hit in candidates:
        text_fingerprint = hashlib.sha256(re.sub(r'\s+', '', hit['text']).encode('utf-8')).hexdigest()
        # Equal text in different files still has different inspectable sources.
        fingerprint = (hit['document_id'], text_fingerprint)
        if fingerprint in seen:
            seen[fingerprint]['duplicate_document_ids'].append(hit['document_id'])
            continue
        hit['duplicate_document_ids'] = []
        seen[fingerprint] = hit
        ranked.append(hit)
    for index, hit in enumerate(ranked, 1):
        hit['cross_document_rank'] = index
    return ranked[:max(top_k, len(per_document_hits)*2) if coverage else top_k]


def query(document_ids: list[str], question: str, top_k: int = 6) -> dict:
    started = perf_counter()
    trace = []

    def step(name, action):
        before = perf_counter()
        try:
            result = action()
        except AppError as error:
            trace.append({'step': name, 'status': 'failed',
                          'duration_ms': round((perf_counter() - before) * 1000)})
            error.trace = trace
            raise
        trace.append({'step': name, 'status': 'success',
                      'duration_ms': round((perf_counter() - before) * 1000)})
        return result

    hits = step('multi_document_search', lambda: retrieve_many(document_ids, question, top_k))
    trace[-1].update(documents=len(set(document_ids)), hits=len(hits))
    context = step('context_build', lambda: [
        {'chunk_id': f"{h['document_id']}:{h['chunk_id']}", 'document': h['filename'],
         'page': h['page'], 'heading_path': h.get('heading_path', []), 'text': h['text']}
        for h in hits])
    multi_guidance = ('多份资料的比较或逐篇概述必须分别说明各份材料的结论，并在 used_chunk_ids 引用每份材料。'
                      'answer 字段只写结论，每份材料最多两句话，总字数尽量不超过 300 字。'
                      '不要罗列课件问题、教学目标、封面或原文整段；不要在 answer 中输出 chunk_id。') if _coverage_question(question) else ''
    if ORIGINAL_PATTERN.search(question):
        multi_guidance = ('用户在索取原文。请逐字摘录 Context 中可核对的正文，不要把译文、注释、背景和课件问题当原文。'
                          '若片段仅覆盖部分正文，就明确说是已检索到的原文节选，并引用相应 chunk_id；不要自行补全。')
    response = step('llm_generate', lambda: generate_answer(question, context,
                     lambda system, payload: chat_json(system + '\n' + multi_guidance, payload)))
    selected = [load_document(identifier) for identifier in dict.fromkeys(document_ids)]
    named = [document for document in selected if _title_matches_question(document, question)]
    targets = named or selected
    expected_documents = {document['document_id'] for document in targets} if _coverage_question(question) else set()
    warnings = []
    used_documents = {item['document_id'] for item in hits
                      if f"{item['document_id']}:{item['chunk_id']}" in response.get('used_chunk_ids', [])}
    if len(expected_documents) > 1 and not expected_documents <= used_documents:
        # A partial citation cannot support a comparison or a "each document"
        # answer. Give the model one focused chance with the balanced context.
        reminder = ('本题要求分别覆盖所选的每份相关材料。比较题必须说明两边的依据；'
                    '逐篇概述题请按文件分点简要概述，不要复述封面或整段原文。'
                    '每份有结论的材料都要引用其 chunk_id；缺少依据时明确说明，不能用一篇代替多篇。')
        try:
            retried = step('llm_recheck', lambda: chat_json(RAG_SYSTEM + '\n' + reminder,
                            json.dumps({'question': question, 'context': context}, ensure_ascii=False)))
        except AppError as error:
            if error.code == 'REQUEST_CANCELLED':
                raise
            warnings.append('多材料补充复核未完成，保留已取得的有效引用。')
            retried = {}
        if isinstance(retried.get('answer'), str) and isinstance(retried.get('used_chunk_ids'), list):
            try:
                normalized = normalize_citations(retried['used_chunk_ids'], {entry['chunk_id'] for entry in context})
                retried_documents = {hit['document_id'] for hit in hits
                                     if f"{hit['document_id']}:{hit['chunk_id']}" in normalized}
                if normalized and retried['answer'].strip() and len(retried_documents) >= len(used_documents) and not is_unknown_answer(retried['answer']):
                    response = {**retried, 'used_chunk_ids': normalized}
            except AppError:
                pass
    def validate_citations():
        used = response.get('used_chunk_ids')
        if not isinstance(response.get('answer'), str) or not isinstance(used, list):
            raise AppError('LLM_INVALID_RESPONSE', '模型返回格式不合法', 502)
        allowed = {item['chunk_id'] for item in context}
        if any(not isinstance(item, str) or item not in allowed for item in used):
            raise AppError('INVALID_SOURCE', '模型引用了不存在的资料片段', 502)
        return used

    used = step('citation_validate', validate_citations)
    sources = [h for h in hits if f"{h['document_id']}:{h['chunk_id']}" in used]
    answer = response['answer'].strip()
    for source in sources:
        for identifier in (f"{source['document_id']}:{source['chunk_id']}", source['chunk_id']):
            answer = re.sub(r'[（(]\s*' + re.escape(identifier) + r'\s*[)）]', '', answer)
            answer = answer.replace(identifier, '')
    cited_documents = {source['document_id'] for source in sources}
    missing_documents = [document for document in targets
                         if document['document_id'] in expected_documents - cited_documents]
    if not sources or not answer or is_unknown_answer(answer):
        answer, sources = '根据所选文档无法确定。', []
    elif missing_documents:
        warning = '以下材料尚未取得有效引用依据：' + '、'.join(document['filename'] for document in missing_documents)
        warnings.append(warning)
        answer += '\n\n' + warning + '。以上结论仅覆盖已引用的材料，尚未覆盖全部指定材料。'
    return {'success': True, 'question': question, 'answer': answer, 'sources': sources,
            'partial': bool(sources and missing_documents), 'warnings': warnings,
            'documents': list(dict.fromkeys(document_ids)),
            'trace': trace, 'latency_ms': round((perf_counter() - started) * 1000)}

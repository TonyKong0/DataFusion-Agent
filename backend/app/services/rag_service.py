import json
import re
import time
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.document_service import load_document
from app.services.vector_store import search, ready
from app.llm.deepseek_client import chat_json
from app.services.rag_answer import generate as generate_answer, is_unknown_answer
from app.services.document_facts import AUTHOR_QUESTION, author_answer, title_matches_question, _display_title
from app.services.document_question import normalize as normalize_document_question, model_correction
from app.services.rag_retrieval import retrieve_candidates

UNKNOWN = '根据当前文档无法确定。'
UNKNOWN_SELECTED = '根据所选文档无法确定。'
INDEXING_STATES = {'uploaded', 'parsing', 'chunking', 'embedding', 'persisting'}
OVERVIEW_PATTERN = re.compile(r'主要内容|关键内容|主要观点|核心观点|主旨|中心思想|思想感情|主要表达|表达.{0,8}(?:思想|情感|观点)|讲述什么|讲(?:的|了)?(?:是)?(?:啥|什么)|概括|概要|总结|大意|主题|关于什么')
AUTHOR_PATTERN = AUTHOR_QUESTION
ORIGINAL_PATTERN = re.compile(r'原文|全文|原句|原段')
ORIGINAL_REQUEST = re.compile(r'(?:原文|全文)(?:是|为|有|内容|什么|吗|呢|[？?。！!]|$)|(?:给出|展示|列出|摘录|提供).{0,12}(?:原文|全文)')
OVERVIEW_CUE = re.compile(r'主旨|中心|主题|思想|观点|情节|结论|总结|概括|小结|表达|体现|揭示|介绍|主要内容')
SLIDE_NOISE = re.compile(r'PPT模板|模板网|WWW\.|www\.|教学课件|学习目标|读一读写一写')
EXPLANATION_CUE = re.compile(r'译文[:：]|译文|注释|背景介绍|写作背景|词语解释|字词解释|教学目标|学习目标|思考题|课堂练习|文体介绍')
LESSON_QUESTION = re.compile(r'第\d+段|第[一二三四五]段|作者在文中|这篇文章|主要内容|主题思想|是什么|为什么|有哪些|如何理解|\b答[:：]')
ORIGINAL_NOTE = re.compile(r'^(?:同[“"「]|译文|注释|词语|解释|疏通文意|阅读理解|背景|思考|练习)')
ORIGINAL_COMMENTARY = re.compile(r'诗人|作者|这句诗|这首诗|形象地|体现了|表达了|课文大意|译文|注释|讲解|主题思想')
VERSE_CONTEXT_EXCLUSION = re.compile(r'明大意|译文|翻译|白话|今译|课文大意|解诗题|晓背景|知作者|类诗探读|群诗联读')
POETRY_DOCUMENT_CUE = re.compile(r'诗歌|古体诗|乐府诗|诗词|诗句|律诗|绝句|诗题|解诗题')
VERSE_COUPLET = re.compile(r'(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{5,7}，'
                           r'[\u4e00-\u9fff]{5,7}[。！？])')


def original_excerpt_answer(documents: list[dict], question: str) -> dict | None:
    """Ground a request for source wording in a visible PDF passage."""
    if not ORIGINAL_REQUEST.search(question):
        return None
    matched = [document for document in documents if title_matches_question(document, question)]
    targets = matched or (documents if len(documents) == 1 else [])
    if len(targets) != 1:
        return None
    document = targets[0]
    candidates = retrieve_original_hits(document, question, 18)
    substantive = []
    for hit in candidates:
        body = str(hit.get('text') or '').strip()
        if (len(body) < 35 or EXPLANATION_CUE.search(body)
                or LESSON_QUESTION.search(body) or SLIDE_NOISE.search(body)
                or len(re.findall(r'[。！？；]', body)) < 2
                or body.count('《') >= 2):
            continue
        substantive.append(hit)
    standalone = [hit for hit in substantive if _looks_like_standalone_original(hit['text'])]
    if standalone:
        source = min(standalone, key=lambda hit: (hit.get('page', 0), hit.get('chunk_id', '')))
        excerpt = _original_lines(source['text'])
    else:
        source, excerpt = _poetry_excerpt(document, candidates)
        if source is None:
            source, excerpt = _select_original_with_model(document, candidates)
    if source is None:
        return None
    if len(excerpt) < 12:
        return None
    answer = (f'在所选材料中找到以下原文节选：\n{excerpt}\n'
              '这里只展示当前可逐字核对的片段；可通过下方引用打开原文件查看其余内容。')
    return {'success': True, 'question': question, 'answer': answer,
            'sources': [{**source, 'document_id': document['document_id'],
                         'filename': document.get('filename', '材料')}],
            'trace': [{'step': 'original_excerpt', 'name': 'original_excerpt', 'status': 'success'}]}


def _original_lines(text: str) -> str:
    lines = []
    for line in str(text).splitlines():
        line = line.strip()
        if lines and ORIGINAL_NOTE.search(line):
            break
        if line:
            lines.append(line)
    return '\n'.join(lines).strip()[:420]


def _looks_like_standalone_original(text: str) -> bool:
    """Use the rule path only for unannotated classical prose, never a slide overview."""
    opening = _original_lines(text)[:110]
    first_line = opening.splitlines()[0] if opening else ''
    if (len(first_line) < 12 or re.search(r'[A-Za-z]', first_line)
            or not re.search(r'[。！？；]', first_line[:55])):
        return False
    if len(opening) < 45 or re.search(r'的|是|了|在|介绍|背景|表达|诗人|作者', opening):
        return False
    return len(re.findall(r'[之其而也者矣焉乎予乃于]', opening)) >= 2


def _verbatim_excerpt(source: str, proposed: str) -> str | None:
    """Recover the exact source span if the model changes only whitespace."""
    compact = re.sub(r'\s+', '', source)
    wanted = re.sub(r'\s+', '', proposed)
    if len(wanted) < 12:
        return None
    index = compact.find(wanted)
    if index < 0:
        return None
    positions = [offset for offset, char in enumerate(source) if not char.isspace()]
    return source[positions[index]:positions[index + len(wanted) - 1] + 1].strip()


def _poetry_excerpt(document: dict, candidates: list[dict]) -> tuple[dict | None, str]:
    """Take a complete 5/7-character couplet without adjacent slide commentary."""
    title = _display_title(document)
    opening_chunks = sorted(document.get('content') or [], key=lambda item: item.get('page', 0))[:12]
    if not any(POETRY_DOCUMENT_CUE.search(str(item.get('text') or '')) for item in opening_chunks):
        return None, ''
    for hit in sorted(candidates, key=lambda item: (item.get('page', 0), item.get('chunk_id', ''))):
        body = str(hit.get('text') or '')
        if SLIDE_NOISE.search(body) or VERSE_CONTEXT_EXCLUSION.search(body) or any(
                name != title for name in re.findall(r'《([^》]+)》', body)):
            continue
        for match in VERSE_COUPLET.finditer(body):
            verse = match.group(1)
            if not re.search(r'的|是|了|在|诗人|作者|表达|表现|介绍', verse):
                return hit, verse
    return None, ''


def _select_original_with_model(document: dict, candidates: list[dict]) -> tuple[dict | None, str]:
    """For mixed slides, require a model-selected passage to occur in the PDF verbatim."""
    title = _display_title(document)
    choices = [{'chunk_id': hit['chunk_id'], 'page': hit['page'],
                'text': str(hit['text'])[:700]} for hit in candidates[:18]]
    if not choices:
        return None, ''
    system = ('你只做原文定位。用户要的是指定作品本身的文字，不是作品介绍、作者生平、'
              '创作背景、译文、注释、讲解或其他作品。请从候选片段中找出一段连续的作品正文，'
              '优先选原文靠前的段落。逐字复制，不要拼接多个片段，不要补写或改字。'
              '短诗句可以只有一行，绝不能把紧跟诗句的讲解文字一并复制。'
              '找不到可靠正文时返回空字符串。只返回JSON对象：'
              '{"chunk_id":"", "excerpt":""}。')
    payload = json.dumps({'work': title, 'candidates': choices}, ensure_ascii=False)
    for attempt in range(2):
        reminder = ('上次给出的文字混入讲解、其他作品或不在材料中。'
                    '这次只摘录一段可核对的本作品原文；单句诗也可以。') if attempt else ''
        try:
            response = chat_json(system + reminder, payload)
        except AppError:
            return None, ''
        chunk_id, proposed = response.get('chunk_id'), response.get('excerpt')
        if not isinstance(chunk_id, str) or not isinstance(proposed, str):
            continue
        source = next((hit for hit in candidates if hit['chunk_id'] == chunk_id), None)
        if not source:
            continue
        other_titles = [name for name in re.findall(r'《([^》]+)》', source['text']) if name != title]
        if other_titles:
            continue
        excerpt = _verbatim_excerpt(str(source['text'])[:700], proposed)
        if excerpt and not ORIGINAL_COMMENTARY.search(excerpt):
            return source, excerpt
    return None, ''


def _overview_quality(hit: dict) -> float:
    text = str(hit.get('text') or '').strip()
    if len(text) < 70:
        return -1.0
    score = float(hit.get('score') or 0)
    score += min(len(text), 450) / 450 * .08
    if OVERVIEW_CUE.search(text):
        score += .09
    if SLIDE_NOISE.search(text):
        score -= .2
    if text.count('？') + text.count('?') >= 2:
        score -= .16
    if re.search(r'思考.{0,8}问题|回答.{0,8}问题|课文感知|课堂练习', text) and not re.search(r'答[:：]', text):
        score -= .1
    return score


def retrieve_original_hits(document: dict, question: str, limit: int) -> list[dict]:
    """Prefer source prose over cover pages, translations and teaching notes."""
    content = document.get('content') or []
    ranked = search(document, question, len(content))

    def quality(hit: dict) -> float:
        body = str(hit.get('text') or '').strip()
        if len(body) < 35:
            return -1.0
        value = float(hit.get('score') or 0) + min(len(body), 500) / 500 * .06
        if len(re.findall(r'[。！？；]', body)) >= 2:
            value += .07
        if EXPLANATION_CUE.search(body):
            value -= .23
        if SLIDE_NOISE.search(body):
            value -= .2
        if body.count('？') + body.count('?') >= 2:
            value -= .12
        if LESSON_QUESTION.search(body):
            value -= .2
        return value

    chosen = [hit for hit in sorted(ranked, key=quality, reverse=True)
              if quality(hit) >= 0][:limit]
    if not chosen:
        chosen = [hit for hit in ranked if len(str(hit.get('text') or '').strip()) >= 12
                  and not EXPLANATION_CUE.search(str(hit.get('text') or ''))
                  and not SLIDE_NOISE.search(str(hit.get('text') or ''))][:limit]
    # A passage spread over several PDF pages reads correctly in source order.
    return sorted(chosen, key=lambda hit: (hit.get('page', 0), hit.get('chunk_id', '')))


def retrieve_hits(document: dict, question: str, limit: int) -> list[dict]:
    """Add opening evidence for document-wide overview and authorship questions."""
    overview = bool(OVERVIEW_PATTERN.search(question))
    authorship = bool(AUTHOR_PATTERN.search(question))
    if not overview and not authorship:
        return retrieve_candidates(document, question, limit, search_fn=search)
    content = document.get('content') or []
    ranked = search(document, question, len(content))
    by_id = {hit['chunk_id']: hit for hit in ranked}
    opening_chunks = [chunk for chunk in content if len(chunk.get('text', '').strip()) >= 80]
    if overview and not opening_chunks:
        opening_chunks = [chunk for chunk in content if chunk.get('text', '').strip()]
    anchors = []
    if authorship and content:
        # Rules only nominate source passages; the generator decides authorship.
        hinted = author_answer([document], question)
        if hinted:
            anchors.extend({**chunk, 'score': by_id.get(chunk['chunk_id'], {}).get('score', 0.0)}
                           for chunk in hinted['sources'])
        first_page = min(chunk.get('page', 1) for chunk in content)
        cover = [chunk for chunk in content if chunk.get('page', 1) == first_page
                 and chunk.get('text', '').strip()]
        cover_text = '\n'.join(chunk['text'] for chunk in cover)
        if (len(cover) > 1 or len(cover_text.splitlines()) > 1
                or re.search(r'作者|编者|主编|编著|撰写|\bby\b', cover_text, re.IGNORECASE)):
            anchors.extend({**chunk, 'score': by_id.get(chunk['chunk_id'], {}).get('score', 0.0)}
                           for chunk in cover[:min(2, limit)]
                           if chunk['chunk_id'] not in {hit['chunk_id'] for hit in anchors})
    if overview:
        # The first pages of a PDF are often a cover or teaching slides. Retrieve
        # theme and substance from the whole index before adding opening context.
        focused = search(document, '这份材料的主要内容、核心观点、主题思想和结论是什么？', len(content))
        ranked_by_id = {hit['chunk_id']: hit for hit in ranked}
        for hit in focused:
            original = ranked_by_id.get(hit['chunk_id'])
            ranked_by_id[hit['chunk_id']] = {**hit,
                'score': .3 * float(hit.get('score') or 0) +
                         .7 * float((original or hit).get('score') or 0)}
        informative = sorted(ranked_by_id.values(), key=_overview_quality, reverse=True)
        ranked = informative
        anchors = [hit for hit in informative if _overview_quality(hit) >= 0][:min(2, limit)]
    for chunk in opening_chunks if authorship else []:
        if len(anchors) >= limit:
            break
        if any(item['chunk_id'] == chunk['chunk_id'] for item in anchors):
            continue
        hit = by_id.get(chunk['chunk_id'])
        anchors.append(hit if hit is not None else {**chunk, 'score': 0.0})
        if len(anchors) >= min(3 if overview else 2, limit):
            break
    selected = {hit['chunk_id'] for hit in anchors}
    candidates = [hit for hit in ranked if hit['chunk_id'] not in selected
                  and len(hit['text'].strip()) >= 50
                  and not ('PPT模板' in hit['text'] and 'www.' in hit['text'])]
    return (anchors + candidates)[:limit] or ranked[:limit]


def query(document_id: str, question: str, top_k: int, *, _allow_rewrite: bool = True) -> dict:
    started = time.perf_counter()
    trace = []

    def step(name, action):
        before = time.perf_counter()
        try:
            result = action()
        except AppError as error:
            trace.append({'step': name, 'name': name, 'status': 'failed', 'duration_ms': round((time.perf_counter()-before)*1000)})
            error.trace = trace
            raise
        trace.append({'step': name, 'name': name, 'status': 'success', 'duration_ms': round((time.perf_counter()-before)*1000)})
        return result

    try:
        document = step('document_load', lambda: load_document(document_id))
        if document['status'] != 'indexed' or not ready(document_id):
            raise AppError('INDEX_NOT_READY', '文档尚未建立索引', 409)
        understood = normalize_document_question(question, [document])
        original = original_excerpt_answer([document], understood)
        if original:
            return {**original, 'question': question, 'document_id': document_id,
                    'document_ids': [document_id],
                    'document_names': [{'document_id': document_id, 'filename': document['filename']}],
                    **({'interpreted_question': understood} if understood != question else {}),
                    'latency_ms': round((time.perf_counter()-started)*1000)}
        formula = _formula_answer(document, understood)
        if formula:
            step('formula_calculated', lambda: True)
            return {'success': True, 'question': question, 'answer': formula['answer'],
                    'document_id': document_id, 'document_ids': [document_id],
                    'document_names': [{'document_id': document_id,
                                        'filename': document.get('filename', document_id)}],
                    'sources': formula['sources'],
                    'formula_calculation': formula['calculation'], 'sql': None, 'data': None,
                    'trace': trace, 'latency_ms': round((time.perf_counter()-started)*1000)}
        retrieval_limit = max(8, top_k) if ORIGINAL_PATTERN.search(understood) else min(top_k, get_settings().rag_top_k)
        hits = step('vector_search', lambda: retrieve_original_hits(document, understood, retrieval_limit)
                    if ORIGINAL_PATTERN.search(understood) else
                    retrieve_hits(document, understood, retrieval_limit))
        context = step('context_build', lambda: [{'chunk_id': h['chunk_id'], 'page': h['page'],
            'heading_path': h.get('heading_path', []), 'text': h['text']} for h in hits])
        output = step('llm_generate', lambda: generate_answer(understood, context, chat_json))
        if not isinstance(output.get('answer'), str) or not isinstance(output.get('used_chunk_ids'), list):
            raise AppError('LLM_INVALID_RESPONSE', '模型返回格式不合法', 502)
        def validate_citations():
            valid_ids = {hit['chunk_id'] for hit in hits}
            claimed = output['used_chunk_ids']
            if any(not isinstance(item, str) or item not in valid_ids for item in claimed):
                raise AppError('INVALID_SOURCE', '模型引用了不存在的资料片段', 502)
            return claimed
        claimed = step('citation_validate', validate_citations)
        sources = [hit for hit in hits if hit['chunk_id'] in set(claimed)]
        answer = output['answer'].strip()
        if not sources or not answer or is_unknown_answer(answer):
            answer, sources = UNKNOWN, []
        if not sources and _allow_rewrite:
            correction = step('question_rewrite', lambda: model_correction(understood, [document], chat_json))
            if correction:
                retried = query(document_id, correction, top_k, _allow_rewrite=False)
                if retried.get('sources'):
                    retried['question'] = question
                    retried['interpreted_question'] = correction
                    retried['trace'] = trace + retried.get('trace', [])
                    retried['latency_ms'] = round((time.perf_counter()-started)*1000)
                    return retried
        return {'success': True, 'question': question, 'answer': answer, 'document_id': document_id,
                **({'interpreted_question': understood} if understood != question else {}),
                'document_ids': [document_id],
                'document_names': [{'document_id': document_id,
                                    'filename': document.get('filename', document_id)}],
                'sources': sources, 'sql': None, 'data': None, 'trace': trace,
                'latency_ms': round((time.perf_counter()-started)*1000)}
    except AppError as error:
        error.trace = trace
        raise


def _formula_answer(document: dict, question: str) -> dict | None:
    if not re.search(r'计算|算出|等于多少|增长率是多少|结果是多少', question):
        return None
    formulas = [item for item in document.get('processing', {}).get('formulas', [])
                if re.split(r'[=＝]', item['raw_text'], maxsplit=1)[0].strip() in question]
    if not formulas:
        return None
    if len(formulas) != 1 or not formulas[0].get('calculation'):
        return {'answer': '公式或参数存在歧义，请指定公式页码并核对参数后再计算。',
                'sources': [], 'calculation': None}
    calculation = formulas[0]['calculation']
    evidence_texts = [calculation['raw_text']] + [item['source_text'] for item in calculation['parameters']]
    evidence_pages = {calculation['page']} | {item['page'] for item in calculation['parameters']}
    sources = [dict(chunk, score=None, source_type='formula_evidence') for chunk in document['content']
               if chunk['page'] in evidence_pages and any(text in chunk['text'] for text in evidence_texts)]
    if not sources or any(not any(text in source['text'] for source in sources) for text in evidence_texts):
        return {'answer': '公式证据未完整进入索引，请重建索引后再计算。',
                'sources': [], 'calculation': None}
    value = calculation['result']
    answer = f"根据文档第 {calculation['page']} 页的公式和参数，计算结果为 {value:g}{calculation['unit']}。"
    return {'answer': answer, 'sources': sources, 'calculation': calculation}


def query_documents(document_ids: list[str] | None, question: str, top_k: int,
                    *, _allow_rewrite: bool = True) -> dict:
    """Query the exact per-turn document scope, preserving cited source metadata."""
    ids = list(dict.fromkeys(document_ids or []))
    if not ids:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '请选择至少一份已索引文档后再提问', 422)
    if len(ids) > 10:
        raise AppError('DOCUMENT_SELECTION_LIMIT', '每轮最多选择 10 份文档', 422)

    documents = []
    for document_id in ids:
        document = load_document(document_id)
        index_state = (document.get('index_status') or {}).get('status')
        if (document.get('status') != 'indexed' or index_state in INDEXING_STATES
                or not ready(document_id)):
            raise AppError('INDEX_NOT_READY', f'{document.get("filename", document_id)} 尚未完成索引，暂不可查询', 409)
        documents.append(document)

    started = time.perf_counter()
    understood = normalize_document_question(question, documents)
    if original := original_excerpt_answer(documents, understood):
        result = original
    elif author := author_answer(documents, understood):
        result = author
    elif len(ids) == 1:
        result = query(ids[0], understood, max(8, top_k) if ORIGINAL_PATTERN.search(understood)
                       else min(top_k, get_settings().rag_top_k),
                       _allow_rewrite=False)
    else:
        from app.document.multi_doc.retriever import _coverage_question, query as query_multiple
        broad = _coverage_question(understood)
        limit = (max(8, len(ids) * 2) if ORIGINAL_PATTERN.search(understood) else
                 max(len(ids) * 2, min(top_k, get_settings().rag_top_k)) if broad else
                 min(top_k, get_settings().rag_top_k))
        result = query_multiple(ids, understood, limit)

    if not result.get('sources') and _allow_rewrite:
        before = time.perf_counter()
        correction = model_correction(understood, documents, chat_json)
        result.setdefault('trace', []).append({'step': 'question_rewrite', 'status': 'success',
            'duration_ms': round((time.perf_counter()-before)*1000)})
        if correction:
            retried = query_documents(ids, correction, top_k, _allow_rewrite=False)
            if retried.get('sources'):
                retried['question'] = question
                retried['interpreted_question'] = correction
                retried['trace'] = result.get('trace', []) + retried.get('trace', [])
                retried['latency_ms'] = round((time.perf_counter()-started)*1000)
                return retried

    result['question'] = question
    if understood != question:
        result['interpreted_question'] = understood

    result['document_ids'] = ids
    result['document_names'] = [{'document_id': document['document_id'],
                                 'filename': document['filename']} for document in documents]
    names = {item['document_id']: item['filename'] for item in result['document_names']}
    metadata = {document['document_id']: {
        'extension': document.get('extension') or document.get('filename', '').rsplit('.', 1)[-1].lower(),
        'preview_available': bool(document.get('preview_available'))} for document in documents}
    fallback_id = ids[0] if len(ids) == 1 else None
    result['sources'] = [{**source,
        'document_id': source.get('document_id') or fallback_id,
        'filename': source.get('filename') or names.get(source.get('document_id') or fallback_id, '材料'),
        **{key: value for key, value in metadata.get(
            source.get('document_id') or fallback_id, {}).items() if key != 'document_id'}}
        for source in result.get('sources', [])]
    return result

"""Validate cited RAG answers and retry a missed answer once against the same evidence."""

import json
import re
from collections.abc import Callable

from app.core.errors import AppError
from app.llm.prompts import RAG_SYSTEM

RECHECK_SYSTEM = RAG_SYSTEM + '''
请再次逐段核对 Context。上一轮没有形成可引用的答案；若片段确有与 Question 直接相关的信息，请简要回答并列出相应 chunk_id。若确实没有证据，仍返回无法确定和空数组。'''

EXCERPT_REQUEST = re.compile(r'原文|原句|哪一段|哪句话|摘录|引用|片段')


def is_unknown_answer(answer: str) -> bool:
    compact = re.sub(r'[\s。！？!?.，,]', '', str(answer))
    return compact in {'根据当前文档无法确定', '根据所选文档无法确定',
                       '当前证据不足无法确认答案', '无法确定'}


def normalize_citations(used_ids: list, allowed_ids: set[str]) -> list[str]:
    """Accept an unprefixed chunk ID only when it identifies one visible hit."""
    aliases: dict[str, str | None] = {}
    for full_id in allowed_ids:
        suffix = full_id.rsplit(':', 1)[-1]
        aliases[suffix] = full_id if suffix not in aliases else None
    normalized = []
    for identifier in used_ids:
        if not isinstance(identifier, str):
            raise AppError('INVALID_SOURCE', '模型引用了不存在的资料片段', 502)
        resolved = identifier if identifier in allowed_ids else aliases.get(identifier)
        if not resolved:
            raise AppError('INVALID_SOURCE', '模型引用了不存在的资料片段', 502)
        normalized.append(resolved)
    return normalized


def _quoted_evidence(question: str, context: list[dict]) -> dict | None:
    """Show a matching source excerpt when the model twice misses visible evidence."""
    # A matching name is not evidence for a requested fact (phone number, date,
    # reason, etc.). Only an explicit request for source wording may quote it.
    if not EXCERPT_REQUEST.search(question):
        return None
    topic = (re.search(r'(?:有关|关于|包含|提到|写到)(.{2,80}?)(?:的)?(?:原文|原句|片段)', question)
             or re.search(r'[“「"]([^”」"]{2,80})[”」"]', question))
    if not topic:
        return None
    term = topic.group(1).removesuffix('的').strip()
    if not term:
        return None
    for hit in context:
        body = hit.get('text') or ''
        position = body.lower().find(term.lower())
        if position < 0:
            continue
        start = max(0, position - 20)
        excerpt = re.sub(r'\s+', ' ', body[start:start + 260]).strip()
        if excerpt:
            prefix = '…' if start else ''
            suffix = '…' if start + 260 < len(body) else ''
            return {'answer': f'资料中找到相关原文：“{prefix}{excerpt}{suffix}”',
                    'used_chunk_ids': [hit['chunk_id']]}
    return None


def generate(question: str, context: list[dict], chat_json: Callable) -> dict:
    if not context:
        return {'answer': '根据当前文档无法确定。', 'used_chunk_ids': []}
    payload = json.dumps({'question': question, 'context': context}, ensure_ascii=False)
    allowed = {item['chunk_id'] for item in context}

    def validate(output: dict) -> dict:
        if not isinstance(output.get('answer'), str) or not isinstance(output.get('used_chunk_ids'), list):
            raise AppError('LLM_INVALID_RESPONSE', '模型返回格式不合法', 502)
        return {**output, 'used_chunk_ids': normalize_citations(output['used_chunk_ids'], allowed)}

    first = validate(chat_json(RAG_SYSTEM, payload))
    if first['used_chunk_ids'] and first['answer'].strip() and not is_unknown_answer(first['answer']):
        return first
    # The answer may be in the third or a later hit; retain all retrieved evidence.
    focused = context
    focused_payload = json.dumps({'question': question, 'context': focused}, ensure_ascii=False)
    try:
        second = validate(chat_json(RECHECK_SYSTEM, focused_payload))
    except AppError as error:
        if error.code == 'REQUEST_CANCELLED':
            raise
        return _quoted_evidence(question, context) or first
    if second['used_chunk_ids'] and second['answer'].strip() and not is_unknown_answer(second['answer']):
        return second
    return _quoted_evidence(question, context) or first

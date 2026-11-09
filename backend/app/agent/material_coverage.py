"""Explicit statements about what the retrieved materials do NOT record.

A generic refusal ("insufficient evidence") does not tell the user whether the
answer is missing, the material was not retrieved, or the tool failed.  When a
document step was required but produced no citable evidence, the answer states
the absence explicitly and separates database facts from material claims.

The statement is a provenance boundary rather than a factual claim: it carries
no evidence_id, contains no numbers, and never invents a value for the missing
item.  It is deterministic so that the behaviour does not depend on the model
happening to phrase an absence well.
"""
from __future__ import annotations

import re

DOCUMENT_MISSING = '缺少document证据'
EXPLICIT_ABSENCE_MARKERS = ('未记载', '未记录', '未提到', '未包含', '未规定', '并未规定')
GENERIC_INSUFFICIENT = '当前证据不足，无法确认答案。'

_TOPIC_PATTERN = re.compile(
    r'(?:文档|材料|手册|资料|数据字典|示例)[^，。？?]{0,6}?'
    r'(?:中的|里|中|规定的|记载的)?(.{2,20}?)'
    r'(?=是多少|是什么|如何|怎样|吗|？|\?|，|,|。|$)'
)


def absence_subject(question: str) -> str:
    """Name the item the user asked about, without pretending to parse semantics."""
    q = (question or '').strip()
    if not q:
        return '本次所问信息'
    matched = _TOPIC_PATTERN.search(q)
    subject = (matched.group(1) if matched else q[:24]).strip(' 的了吗？?，,。')
    return subject or '本次所问信息'


def material_coverage_note(question: str = '', *, has_claims: bool = False) -> str:
    subject = absence_subject(question)
    scope = ('以上结论仅来自数据库，不代表材料中的记载。' if has_claims
             else '本次未形成可引用的文档结论。')
    return (f'所检索材料中未记载「{subject}」的文档侧依据，文档侧证据不足，'
            f'无法据此形成文档结论；{scope}')


def needs_material_coverage(fusion: dict | None, answer: str) -> bool:
    """Only when a document step was required and no explicit absence is present."""
    missing = (fusion or {}).get('missing') or []
    if DOCUMENT_MISSING not in missing:
        return False
    return not any(marker in (answer or '') for marker in EXPLICIT_ABSENCE_MARKERS)

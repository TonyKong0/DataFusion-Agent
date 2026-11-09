"""Conservative question correction for material retrieval.

Only intent wording and titles of the selected documents can be changed locally.
An optional model retry is used after an unanswered search; it never supplies facts.
"""

import json
import re
from collections.abc import Callable
from difflib import SequenceMatcher

from app.core.errors import AppError


INTENT_PHRASES = ('作者是谁', '主要内容', '主要讲什么', '讲的是什么', '写的是什么',
                  '什么时候', '在哪里', '为什么', '如何理解', '有什么区别')
REWRITE_SYSTEM = '''你只纠正用户材料问题中的明显错别字、口误和不通顺语序，不回答问题。
保留原意、数字、限定条件和选中文档范围。只有输入中的标题明显指向所选文件时，才可修正标题。
不能补充用户没有问的事实或凭常识替换人物、作品。无法确定时原样返回。
只输出 JSON：{"corrected_question":""}。'''


def _distance_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = sorted((left, right), key=len)
    return any(long[:index] + long[index + 1:] == short for index in range(len(long)))


def _correct_phrase(question: str, phrase: str) -> str:
    if phrase in question:
        return question
    for size in (len(phrase), len(phrase) - 1, len(phrase) + 1):
        for start in range(len(question) - size + 1):
            part = question[start:start + size]
            # Keep the intent anchor so a valid but different question is not changed.
            if part[:2] == phrase[:2] and _distance_one(part, phrase):
                return question[:start] + phrase + question[start + size:]
    return question


def normalize(question: str, documents: list[dict]) -> str:
    result = question.strip()
    for phrase in INTENT_PHRASES:
        result = _correct_phrase(result, phrase)
    titles = []
    for document in documents:
        stem = (document.get('filename') or '').rsplit('.', 1)[0]
        titles.extend(re.findall(r'[\u4e00-\u9fff]{4,}', stem))
    titles = set(titles)
    if not any(title in result for title in titles):
        candidates = {_correct_phrase(result, title) for title in titles}
        candidates.discard(result)
        if len(candidates) == 1:
            result = candidates.pop()
    return result


def model_correction(question: str, documents: list[dict], chat_json: Callable) -> str | None:
    """Suggest a small rewrite only; callers must run retrieval and cite evidence again."""
    filenames = [document.get('filename', '') for document in documents]
    try:
        output = chat_json(REWRITE_SYSTEM, json.dumps(
            {'question': question, 'selected_files': filenames}, ensure_ascii=False))
    except AppError as error:
        if error.code == 'REQUEST_CANCELLED':
            raise
        return None
    corrected = output.get('corrected_question')
    if not isinstance(corrected, str):
        return None
    corrected = corrected.strip()
    if (not corrected or corrected == question or len(corrected) > 200
            or SequenceMatcher(None, question, corrected).ratio() < .6
            or re.findall(r'\d+', question) != re.findall(r'\d+', corrected)):
        return None
    quoted = re.findall(r'《([^》]+)》', corrected)
    if quoted and any(not any(title in filename for filename in filenames) for title in quoted):
        return None
    return corrected

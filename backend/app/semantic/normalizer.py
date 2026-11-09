"""Conservative question rewrite with an auditable change list."""

import re

from app.semantic.alias_resolver import resolve_aliases


_NUMBER_WORDS = {'十': 10, '二十': 20, '一': 1, '二': 2, '三': 3, '四': 4,
                 '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_NUMBER_PATTERN = re.compile(r'(?<=[前第的])(?:二十|十[一二三四五六七八九]?|[一二三四五六七八九]十?[一二三四五六七八九]?|[一二三四五六七八九])(?=[个首条位名张])')


def _number_value(word: str) -> int:
    if word in _NUMBER_WORDS:
        return _NUMBER_WORDS[word]
    if '十' in word:
        left, right = word.split('十', 1)
        return (int(_NUMBER_WORDS[left]) if left else 1) * 10 + (int(_NUMBER_WORDS[right]) if right else 0)
    return int(_NUMBER_WORDS[word])


def normalize_question(question: str) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError('question must be non-empty')
    original = question.strip()
    result, changes = resolve_aliases(original)

    def convert(match: re.Match) -> str:
        raw = match.group()
        value = str(_number_value(raw))
        changes.append({'type': 'number', 'from': raw, 'to': value})
        return value

    result = _NUMBER_PATTERN.sub(convert, result)
    result = re.sub(r'(?<=查询)(?=[A-Za-z])', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return {'original_question': original, 'normalized_question': result, 'changes': changes}

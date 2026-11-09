"""Small, dependency-free helpers for values carried between agent steps."""
import re


def _source_contains_number(text: str, value: int | float | str) -> bool:
    return re.search(rf'(?<![\d.]){re.escape(str(value))}(?![\d.])', text) is not None


def _extract_number(data: dict):
    answer = str(data.get('answer') or '')
    sources = data.get('sources') or []
    # A number is usable only if the cited original snippet contains it.
    candidates = re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', answer)
    for value in candidates:
        if any(_source_contains_number(str(source.get('text') or ''), value) for source in sources):
            return float(value) if '.' in value else int(value)
    return None


def _primary_value(data: dict):
    rows = data.get('rows') or []
    columns = data.get('columns') or []
    if not rows or not columns:
        return None
    first = rows[0]
    if isinstance(first, dict):
        return first.get(columns[0])
    if isinstance(first, (list, tuple)):
        return first[0] if first else None
    return None

"""Merge exact dictionary, deterministic rule, and LLM elements."""

from dataclasses import replace

from app.semantic.models import Element


def merge_elements(elements: list[Element]) -> dict:
    grouped: dict[tuple[str, str | None], list[Element]] = {}
    for item in elements:
        grouped.setdefault((item.type, item.name), []).append(item)
    merged = []
    conflicts = []
    for (kind, name), group in grouped.items():
        distinct = {repr(item.canonical_value) for item in group}
        if len(distinct) > 1:
            conflicts.append({'type': kind, 'name': name,
                              'values': [item.canonical_value for item in group]})
            merged.extend(replace(item, confidence=min(item.confidence, 0.6)) for item in group)
        else:
            merged.append(max(group, key=lambda item: item.confidence))
    return {'elements': merged, 'conflicts': conflicts}

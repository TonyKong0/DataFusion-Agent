"""Deterministic, manually maintained exact aliases."""

import re

from app.semantic.config_loader import load_config


def resolve_aliases(question: str) -> tuple[str, list[dict]]:
    aliases = load_config('aliases.yaml')
    entries = []
    for category, values in aliases.items():
        for canonical, definition in values.items():
            for raw in definition['aliases']:
                if raw != canonical:
                    entries.append((str(raw), str(canonical), category))
    entries.sort(key=lambda entry: len(entry[0]), reverse=True)
    changes = []
    result = question
    for raw, canonical, category in entries:
        boundary = r'(?<![A-Za-z])' if raw.isascii() else ''
        ending = r'(?![A-Za-z])' if raw.isascii() else (r'(?!曲|词|单|手)' if raw == '歌' else '')
        pattern = re.compile(boundary + re.escape(raw) + ending, re.IGNORECASE if raw.isascii() else 0)
        result, count = pattern.subn(canonical, result)
        if count:
            changes.append({'type': 'alias', 'category': category, 'from': raw, 'to': canonical})
    return result, changes

"""One bounded fallback; every proposed heading must occur verbatim on its page."""
import json
from app.core.errors import AppError
from app.document.structure.models import Heading
from app.llm.deepseek_client import chat_json

SYSTEM = ('识别文档标题。只从给定的原文候选中选取，不改写标题，不编造页码。'
          '只返回 JSON：{"headings":[{"title":"原文标题","page":1,"level":1}]}。'
          'level 只能是 1、2、3；无法确定时返回空数组。')


def fallback_headings(pages: list) -> list[Heading]:
    candidates = []
    for page in pages:
        for line in page.text.splitlines():
            line = line.strip()
            if 3 <= len(line) <= 55 and not line.endswith(('。', '，', ',', '.', ';', '；')):
                candidates.append({'page': page.page, 'title': line})
            if len(candidates) >= 30:
                break
        if len(candidates) >= 30:
            break
    if len(candidates) < 2:
        return []
    try:
        output = chat_json(SYSTEM, json.dumps({'candidates': candidates}, ensure_ascii=False))
    except AppError:
        return []
    if not isinstance(output.get('headings'), list):
        return []
    allowed = {(item['page'], item['title']) for item in candidates}
    headings = []
    for item in output.get('headings', [])[:30]:
        if not isinstance(item, dict):
            continue
        page, title, level = item.get('page'), item.get('title'), item.get('level')
        if type(page) is int and type(title) is str and type(level) is int and level in (1, 2, 3) and (page, title) in allowed:
            headings.append(Heading(title, level, page, None, .60))
    return headings

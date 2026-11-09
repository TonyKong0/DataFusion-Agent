"""Single-table, deterministic element extraction without an LLM."""

import json
import re

from app.semantic.config_loader import load_config
from app.semantic.models import Element
from app.semantic.normalizer import normalize_question
from app.semantic.element_merger import merge_elements
from app.llm.deepseek_client import chat
from app.core.errors import AppError


_ENTITIES = {
    'Customer': ('客户', '顾客', 'customer'),
    'Employee': ('员工', '雇员', 'employee'),
    'Artist': ('艺术家', '音乐家', '艺人', '歌手', 'artist'),
    'Track': ('歌曲', '曲目', '音乐', 'track'),
    'Album': ('专辑', 'album'),
    'Genre': ('音乐类型', '流派', '曲风', 'genre', '类型'),
    'Invoice': ('订单', '发票', 'invoice'),
    'RetailTransaction': ('零售交易', '零售订单', '零售记录', '零售商品', '退货记录',
                          'retail_transaction'),
}
_LIMIT = re.compile(r'前\s*(\d{1,3})\s*(?:个|首|条|位|名|张)?')
_COUNT_LIMIT = re.compile(r'(?<!\d)(\d{1,3})\s*(?:个|首|条|位|名|张)(?=客户|员工|艺术家|歌曲|曲目|专辑|订单)')
_LIMIT_CUES = ('查询', '显示', '列出', '展示', '给我', '看', '找', '推荐', '最高', '最低')
_YEAR = re.compile(r'(?<!\d)(\d{4})\s*年')


def _contains(text: str, alias: str) -> bool:
    if alias == '音乐':
        return bool(re.search(r'音乐(?!类型|流派|家)', text))
    if alias.isascii():
        return bool(re.search(r'(?<![A-Za-z])' + re.escape(alias) + r'(?![A-Za-z])', text, re.I))
    return alias in text


def extract_rule_elements(question: str, normalized_question: str | None = None) -> list[Element]:
    normalized = normalized_question or normalize_question(question)['normalized_question']
    elements = []
    for canonical, names in _ENTITIES.items():
        raw = next((name for name in names if _contains(question, name) or _contains(normalized, name)), None)
        if raw:
            elements.append(Element('entity', canonical, 'rule', 0.95, raw_value=raw))

    aliases = load_config('aliases.yaml')
    for category in ('country', 'genre'):
        for canonical, definition in aliases.get(category, {}).items():
            raw = next((alias for alias in definition['aliases'] if _contains(question, alias)), None)
            if raw:
                elements.append(Element('filter', canonical, 'dictionary', 1.0,
                                        name=category, raw_value=raw))

    limit = _LIMIT.search(normalized)
    if not limit:
        counted = _COUNT_LIMIT.search(normalized)
        if counted and any(cue in normalized[:counted.start()] for cue in _LIMIT_CUES):
            limit = counted
    if limit:
        value = int(limit.group(1))
        if 0 < value <= 100:
            elements.append(Element('limit', value, 'rule', 0.95, raw_value=limit.group()))

    for raw, direction in (('价格最高', 'DESC'), ('最高', 'DESC'),
                           ('价格最低', 'ASC'), ('最低', 'ASC')):
        if raw in normalized:
            elements.append(Element('sort', direction, 'rule', 0.95,
                                    name='price' if '价格' in raw else None, raw_value=raw))
            break

    if any(term in normalized for term in ('多少', '数量', '总数', '一共')) and not any(
        term in normalized for term in ('增长率', '同比', '环比', '价格', '销量')):
        elements.append(Element('metric', 'count', 'rule', 0.95, raw_value='count'))

    years = _YEAR.findall(normalized)
    if years:
        value = years[0] if len(years) == 1 else [years[0], years[1]]
        elements.append(Element('time', value, 'rule', 0.95, name='year', raw_value='、'.join(years[:2])))
    return elements


_FUZZY_TERMS = ('卖得比较猛', '卖得好', '热门', '火爆', '表现好')
_EXTRACT_SYSTEM = '''从用户的单表查询中补充规则未识别的要素。只输出 JSON 对象：
{"elements":[{"type":"metric|sort|entity|filter|limit|time","name":null,"raw_value":"问题原文片段","canonical_value":"值"}]}。
不要编造问题未提到的条件；entity 只允许 Customer/Employee/Artist/Track/Album/Genre/Invoice/RetailTransaction；sort 只允许 ASC/DESC；metric 只允许 count/sales；不能推断多表关系。'''


def needs_fallback(question: str, rules: list[Element]) -> bool:
    return not any(item.type == 'entity' for item in rules) or any(term in question for term in _FUZZY_TERMS)


def _parse_llm_elements(payload: str) -> list[Element]:
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get('elements'), list):
        raise ValueError('elements must be a list')
    parsed = []
    for item in data['elements']:
        if not isinstance(item, dict) or item.get('type') not in {'entity', 'filter', 'metric', 'sort', 'limit', 'time'}:
            raise ValueError('invalid element')
        kind, value = item['type'], item.get('canonical_value')
        if kind == 'entity' and value not in _ENTITIES:
            raise ValueError('unsupported entity')
        if kind == 'sort' and value not in {'ASC', 'DESC'}:
            raise ValueError('unsupported sort')
        if kind == 'metric' and value not in {'count', 'sales'}:
            raise ValueError('unsupported metric')
        if kind == 'limit' and (not isinstance(value, int) or isinstance(value, bool) or not 0 < value <= 100):
            raise ValueError('unsupported limit')
        if kind == 'filter' and (item.get('name') not in {'country', 'genre'} or
                                  value not in load_config('aliases.yaml').get(item['name'], {})):
            raise ValueError('unsupported filter')
        if kind == 'time' and not (isinstance(value, str) and re.fullmatch(r'\d{4}', value)):
            raise ValueError('unsupported time')
        raw = item.get('raw_value')
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('missing evidence')
        parsed.append(Element(kind, value, 'llm', 0.8, name=item.get('name'), raw_value=raw))
    return parsed


def extract_elements(question: str, normalized_question: str | None = None) -> dict:
    normalized = normalized_question or normalize_question(question)['normalized_question']
    rules = extract_rule_elements(question, normalized)
    if not needs_fallback(question, rules):
        return {**merge_elements(rules), 'fallback_used': False, 'error': None}
    for _ in range(2):
        try:
            response = chat(_EXTRACT_SYSTEM, json.dumps({'question': question,
                            'normalized_question': normalized}, ensure_ascii=False), json_mode=True)
            llm_elements = _parse_llm_elements(response)
            return {**merge_elements(rules + llm_elements), 'fallback_used': True, 'error': None}
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        except AppError:
            break
    return {**merge_elements(rules), 'fallback_used': True, 'error': 'ELEMENT_EXTRACTION_FAILED'}

"""Phase 12 rewrite cases guard against invented constraints."""

import pytest

from app.semantic.normalizer import normalize_question


@pytest.mark.parametrize(('question', 'expected'), [
    ('给我瞅瞅美国客户', '查询 USA客户'),
    ('给我看看最贵的十首歌', '查询价格最高的10首歌曲'),
    ('摇滚乐有哪些', 'Rock有哪些'),
    ('爵士乐有哪些', 'Jazz有哪些'),
    ('美利坚客户', 'USA客户'),
    ('US 的客户', 'USA 的客户'),
    ('rock 歌曲', 'Rock 歌曲'),
    ('前五个客户', '前5个客户'),
    ('前二十首歌曲', '前20首歌曲'),
    ('前十二首歌曲', '前12首歌曲'),
    ('价格最低的歌曲', '价格最低的歌曲'),
    ('最便宜的歌', '价格最低的歌曲'),
    ('查询加拿大客户', '查询 Canada客户'),
    ('列出全部艺术家', '列出全部艺术家'),
    ('十年间的歌', '十年间的歌曲'),
    ('音乐类型有多少', '音乐类型有多少'),
])
def test_normalization(question, expected):
    result = normalize_question(question)
    assert result['original_question'] == question
    assert result['normalized_question'] == expected


def test_changes_are_auditable():
    result = normalize_question('瞅瞅美国的前十个客户')
    assert {item['type'] for item in result['changes']} == {'alias', 'number'}
    assert '前10个' in result['normalized_question']


def test_does_not_invent_constraints():
    assert normalize_question('客户')['normalized_question'] == '客户'

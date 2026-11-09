import pytest

from app.semantic.element_extractor import extract_rule_elements


@pytest.mark.parametrize(('question', 'expected'), [
    ('给我看美国的前10个客户', {'entity': 'Customer', 'filter': 'USA', 'limit': 10}),
    ('加拿大客户', {'entity': 'Customer', 'filter': 'Canada'}),
    ('美利坚顾客', {'entity': 'Customer', 'filter': 'USA'}),
    ('Rock 歌曲', {'entity': 'Track', 'filter': 'Rock'}),
    ('摇滚乐曲目', {'entity': 'Track', 'filter': 'Rock'}),
    ('爵士乐歌曲', {'entity': 'Track', 'filter': 'Jazz'}),
    ('艺术家有哪些', {'entity': 'Artist'}),
    ('员工有哪些', {'entity': 'Employee'}),
    ('专辑有哪些', {'entity': 'Album'}),
    ('音乐类型有哪些', {'entity': 'Genre'}),
    ('订单有哪些', {'entity': 'Invoice'}),
    ('前5个客户', {'entity': 'Customer', 'limit': 5}),
    ('前二十首歌曲', {'entity': 'Track', 'limit': 20}),
    ('价格最高的前10首歌曲', {'entity': 'Track', 'sort': 'DESC', 'limit': 10}),
    ('价格最低的歌曲', {'entity': 'Track', 'sort': 'ASC'}),
    ('一共有多少个艺术家', {'entity': 'Artist', 'metric': 'count'}),
    ('一共有多少音乐家，他们分别是谁', {'entity': 'Artist', 'metric': 'count'}),
    ('最流行的音乐', {'entity': 'Track'}),
    ('客户数量是多少', {'entity': 'Customer', 'metric': 'count'}),
    ('2020年的订单', {'entity': 'Invoice', 'time': '2020'}),
    ('2020年至2022年的订单', {'entity': 'Invoice', 'time': ['2020', '2022']}),
    ('普通客户', {'entity': 'Customer'}),
    ('查询美国的客户', {'entity': 'Customer', 'filter': 'USA'}),
    ('给我看看最贵的十首歌', {'entity': 'Track', 'sort': 'DESC', 'limit': 10}),
    ('显示10首歌曲', {'entity': 'Track', 'limit': 10}),
])
def test_rule_extraction(question, expected):
    elements = extract_rule_elements(question)
    actual = {item.type: item.canonical_value for item in elements}
    assert actual == expected
    assert all(item.source in {'dictionary', 'rule'} for item in elements)
    assert all(item.confidence in {1.0, 0.95} for item in elements)


def test_no_llm_for_rule_extraction(monkeypatch):
    from app.llm import deepseek_client
    monkeypatch.setattr(deepseek_client, 'chat_json', lambda *args: pytest.fail('LLM called'))
    extract_rule_elements('前10个客户')


def test_factual_count_is_not_a_limit():
    assert all(item.type != 'limit' for item in extract_rule_elements('客户有10个订单'))

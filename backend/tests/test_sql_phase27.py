from app.services import multitable_service
from app.services.multitable_service import is_multitable_intent
from tests.test_sql_phase26 import SCHEMA
from app.core.errors import AppError


def test_intent_keeps_v1_single_table():
    assert not is_multitable_intent('查询前3首歌曲')
    assert is_multitable_intent('每个客户消费了多少钱')
    assert is_multitable_intent('哪个音乐类型卖出的歌曲数量最多')
    assert is_multitable_intent('歌手 AC/DC 有多少张专辑')


def test_customer_invoice_query_with_real_join_plan(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    monkeypatch.setattr(multitable_service, 'chat_json', lambda *_: {'query': {
        'table': 'customer',
        'select': [
            {'kind': 'column', 'field': {'table': 'customer', 'column': 'CustomerId'}},
            {'kind': 'column', 'field': {'table': 'customer', 'column': 'FirstName'}},
            {'kind': 'aggregate', 'function': 'SUM',
             'field': {'table': 'invoice', 'column': 'Total'}, 'alias': 'spent'},
        ],
        'group_by': [
            {'table': 'customer', 'column': 'CustomerId'},
            {'table': 'customer', 'column': 'FirstName'},
        ],
        'order_by': [{'field': 'spent', 'direction': 'DESC'}],
        'limit': 10,
    }})
    monkeypatch.setattr(multitable_service, 'execute_multitable_sql', lambda sql: (['CustomerId', 'FirstName', 'spent'],
                                                                        [[1, 'Alice', 42.0]]))
    monkeypatch.setattr(multitable_service, 'chat', lambda *_: 'Alice 消费了 42 元。')
    response = multitable_service.query('每个客户消费了多少钱')
    assert response['row_count'] == 1
    assert response['sql_validation']['valid']
    assert set(response['schema_linking']['selected_tables']) == {'customer', 'invoice'}
    assert len(response['join_plan']['join_path']) == 1
    assert all(item['status'] == 'success' for item in response['trace'])
    assert 'SUM' in response['sql']


def test_genre_sales_query_uses_three_real_tables(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    monkeypatch.setattr(multitable_service, 'chat_json', lambda *_: {'query': {
        'table': 'genre',
        'select': [
            {'kind': 'column', 'field': {'table': 'genre', 'column': 'Name'}},
            {'kind': 'aggregate', 'function': 'SUM',
             'field': {'table': 'invoiceline', 'column': 'Quantity'}, 'alias': 'sold'},
        ],
        'group_by': [{'table': 'genre', 'column': 'Name'}],
        'order_by': [{'field': 'sold', 'direction': 'DESC'}],
        'limit': 5,
    }})
    monkeypatch.setattr(multitable_service, 'execute_multitable_sql', lambda sql: (['Name', 'sold'], [['Rock', 100]]))
    monkeypatch.setattr(multitable_service, 'chat', lambda *_: 'Rock 最多。')
    response = multitable_service.query('哪个音乐类型卖出的歌曲数量最多')
    assert response['join_plan']['join_tables'] == ['genre', 'track', 'invoiceline']
    assert len(response['join_plan']['join_path']) == 2
    assert response['rows'] == [['Rock', 100]]


def test_verified_genre_sales_rows_survive_answer_model_failure(monkeypatch):
    monkeypatch.setattr(multitable_service, 'get_metadata', lambda: SCHEMA)
    monkeypatch.setattr(multitable_service, 'chat_json', lambda *_: {'query': {
        'table': 'genre',
        'select': [
            {'kind': 'column', 'field': {'table': 'genre', 'column': 'Name'}},
            {'kind': 'aggregate', 'function': 'SUM',
             'field': {'table': 'invoiceline', 'column': 'Quantity'}, 'alias': 'sold'},
        ],
        'group_by': [{'table': 'genre', 'column': 'Name'}],
        'order_by': [{'field': 'sold', 'direction': 'DESC'}],
        'limit': 1,
    }})
    monkeypatch.setattr(multitable_service, 'execute_multitable_sql',
                        lambda sql: (['Name', 'sold'], [['Rock', 100]]))
    monkeypatch.setattr(multitable_service, 'chat',
                        lambda *_: (_ for _ in ()).throw(AppError('LLM_REQUEST_FAILED', 'unavailable', 502)))

    response = multitable_service.query('销量最高的音乐类型是哪种？')

    assert response['answer'] == '按购买数量衡量，销量最高的音乐类型是 Rock，售出 100 份。'
    assert response['rows'] == [['Rock', 100]]

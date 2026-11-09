"""SQL semantic guard: constrain the answer, never widen the SQL (no LLM calls)."""

import json

import pytest

from app.llm.prompts import ANSWER_SYSTEM
from app.services import answer_semantic_guard as guard
from app.services import nl2sql_service
from app.sql.query_dsl import compile_query_dsl

# Regression fixture transcribed from the 2026-11-05 live run described in
# 《第三次双周报》4.9: SQL was a WHERE-level comparison, the prose claimed an
# aggregate conclusion ("消费总额均高于全体客户平均消费额").
FIXTURE_SQL = (
    'SELECT c.FirstName FROM Customer AS c '
    'JOIN Invoice AS i ON c.CustomerId = i.CustomerId '
    'WHERE i.Total > (SELECT AVG(Total) FROM Invoice) LIMIT 100')
OVERREACH_ANSWER = ('符合条件的客户共 3 位：Luís、Leonie、Astrid。\n\n'
                    '这些客户的消费总额均高于全体客户平均消费额。')
HAVING_SQL = ('SELECT CustomerId, SUM(Total) AS s FROM Invoice GROUP BY CustomerId '
              'HAVING SUM(Total) > (SELECT AVG(Total) FROM Invoice)')
PLAIN_SQL = 'SELECT COUNT(*) AS total FROM Customer'
INVOICE_SCHEMA = [{'table': 'Invoice', 'columns': [
    {'name': 'InvoiceId'}, {'name': 'CustomerId'}, {'name': 'InvoiceDate'}, {'name': 'Total'},
]}]
GENRE_SCHEMA = [{'table': 'genre', 'columns': [
    {'name': 'GenreId', 'type': 'int'}, {'name': 'Name', 'type': 'varchar(120)'}]}]


def test_row_level_subquery_semantics_are_extracted():
    tags = guard.sql_semantics(FIXTURE_SQL)

    assert tags['parse_ok'] is True
    assert tags['has_scalar_subquery'] is True
    assert tags['comparison_level'] == 'row_level'
    assert tags['aggregate'] == 'AVG'
    assert tags['aggregate_table'] == 'Invoice'
    assert tags['compared_expression'] == 'i.Total'
    assert '行级 WHERE 比较' in tags['proof_scope']


def test_having_subquery_is_aggregate_level():
    tags = guard.sql_semantics(HAVING_SQL)

    assert tags['comparison_level'] == 'aggregate_level'
    assert tags['outer_group_by'] is True


def test_plain_select_has_no_comparison_ambiguity():
    tags = guard.sql_semantics(PLAIN_SQL)

    assert tags['has_scalar_subquery'] is False
    assert tags['comparison_level'] == 'plain'


def test_unparseable_sql_fails_closed_as_unknown():
    assert guard.sql_semantics('NOT A SELECT')['comparison_level'] == 'unknown'


def test_november_fifth_overreach_fixture_is_blocked():
    judged = guard.guard_answer(OVERREACH_ANSWER, FIXTURE_SQL)

    assert judged['guarded'] is True
    assert '消费总额' not in judged['answer']
    assert '超出本次查询可证明的范围' in judged['answer']
    assert guard.BLOCKED_WARNING in judged['warnings'][0]
    assert judged['blocked_phrases']


def test_provable_client_names_survive_the_guard():
    judged = guard.guard_answer(OVERREACH_ANSWER, FIXTURE_SQL)

    assert 'Luís' in judged['answer']
    assert '3 位' in judged['answer']


def test_compliant_row_level_wording_is_not_blocked():
    answer = '本次查询返回 3 张发票，其单笔金额高于全体发票平均金额。'

    judged = guard.guard_answer(answer, FIXTURE_SQL)

    assert judged['guarded'] is False
    assert judged['answer'] == answer


def test_demo_question_wording_is_not_affected():
    answer = ('单笔金额高于全体发票平均金额的客户姓名为：Luís、Leonie、Astrid；'
              '本次比较为单笔发票明细级，不代表客户消费总额达标。')

    judged = guard.guard_answer(answer, FIXTURE_SQL)

    # The explicit negation is a scope disclaimer, not an over-claim.
    assert judged['guarded'] is False
    assert judged['answer'] == answer


def test_universal_entity_claim_without_amount_word_is_blocked():
    answer = '符合条件的客户共 3 位。\n这些客户都高于全体客户平均消费额。'

    judged = guard.guard_answer(answer, FIXTURE_SQL)

    assert judged['guarded'] is True
    assert '都高于' not in judged['answer']


def test_aggregate_level_sql_keeps_its_legitimate_conclusion():
    answer = '这些客户的消费总额均高于全体客户平均消费额。'

    judged = guard.guard_answer(answer, HAVING_SQL)

    assert judged['guarded'] is False
    assert judged['answer'] == answer


def test_plain_sql_never_triggers_the_guard():
    judged = guard.guard_answer(OVERREACH_ANSWER, PLAIN_SQL)

    assert judged['guarded'] is False
    assert judged['answer'] == OVERREACH_ANSWER


def test_answer_prompt_states_the_row_level_constraint():
    assert 'comparison_level=row_level' in ANSWER_SYSTEM
    assert '总额达标' in ANSWER_SYSTEM


def test_generate_guarded_answer_passes_semantics_to_the_model():
    captured = []

    def fake_chat(system, user):
        captured.append((system, json.loads(user)))
        return OVERREACH_ANSWER

    judged = guard.generate_guarded_answer(
        '查询消费总额高于全体客户平均消费额的客户姓名', FIXTURE_SQL,
        ['FirstName'], [['Luís']], chat_fn=fake_chat)

    assert captured[0][0] == ANSWER_SYSTEM
    assert captured[0][1]['sql_semantics']['comparison_level'] == 'row_level'
    assert judged['guarded'] is True
    assert '消费总额' not in judged['answer']


def test_controlled_dsl_compiled_sql_is_also_guarded():
    dsl = {'table': 'Invoice',
           'select': [{'kind': 'column', 'field': {'column': 'InvoiceId'}}],
           'filters': {'field': {'column': 'Total'}, 'operator': 'gt',
                       'subquery': {'aggregate': 'AVG', 'field': {'column': 'Total'}}},
           'limit': 50}

    compiled = compile_query_dsl(dsl, INVOICE_SCHEMA)

    assert 'SELECT AVG' in compiled.sql.upper()
    assert guard.guard_answer(OVERREACH_ANSWER, compiled.sql)['guarded'] is True


def test_nl2sql_service_answer_prompt_carries_sql_semantics(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: GENRE_SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {
        'query': {'table': 'genre', 'select': [
            {'kind': 'column', 'field': {'column': 'GenreId'}},
            {'kind': 'column', 'field': {'column': 'Name'}}]}})
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['GenreId', 'Name'], [[1, 'Rock']]))
    calls = []
    monkeypatch.setattr(nl2sql_service, 'chat', lambda system, user:
                        calls.append(user) or '第一种音乐类型是 Rock。')

    result = nl2sql_service.query('查看音乐类型编号和名称')

    assert result['answer'] == '第一种音乐类型是 Rock。'
    assert result['answer_guard']['guarded'] is False
    assert json.loads(calls[0])['sql_semantics']['comparison_level'] == 'plain'


def test_nl2sql_service_blocks_overreach_from_the_answer_model(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: INVOICE_SCHEMA)
    monkeypatch.setattr(nl2sql_service, 'chat_json', lambda *_: {
        'query': {'table': 'Invoice', 'select': [
            {'kind': 'column', 'field': {'column': 'InvoiceId'}}],
            'filters': {'field': {'column': 'Total'}, 'operator': 'gt',
                        'subquery': {'aggregate': 'AVG',
                                     'field': {'column': 'Total'}}}}})
    monkeypatch.setattr(nl2sql_service, 'execute_sql', lambda sql:
                        (['InvoiceId'], [[1], [2]]))
    monkeypatch.setattr(nl2sql_service, 'chat', lambda *_: OVERREACH_ANSWER)

    result = nl2sql_service.query('查询金额高于平均金额的发票')

    assert result['answer_guard']['guarded'] is True
    assert '消费总额' not in result['answer']
    assert '行级 WHERE 比较' in result['answer']


@pytest.mark.parametrize('answer', [
    '数据库中没有符合条件的记录。',
    '本次查询返回 2 行，以下是前 2 行：\n- 发票编号：1；\n- 发票编号：2。',
    '单笔发票金额高于全体发票平均金额。',
])
def test_routine_answers_are_not_false_positives(answer):
    assert guard.guard_answer(answer, FIXTURE_SQL)['guarded'] is False

import pytest

from app.agent.planner import create_plan
from app.agent.router import route_query


def test_database_domain_mentioned_inside_document_question_stays_document_only():
    question = '请说明这份文档如何介绍 Chinook 数据库中的 Invoice 表。'

    routing = route_query(question, allow_llm=False)

    assert routing['route'] == 'DOCUMENT_ONLY'
    assert routing['required_tools'] == ['document_search']


def test_document_question_that_explicitly_requests_a_database_fact_routes_cross_source():
    question = '请查一下数据库里有多少客户，并对照文档中记录的客户数。'

    routing = route_query(question, allow_llm=False)
    plan = create_plan(question, routing)

    assert routing['route'] == 'CROSS_SOURCE'
    assert routing['required_tools'] == ['database_query', 'document_search']
    assert [step.tool for step in plan.steps] == ['database_query', 'document_search']


def test_database_count_without_document_context_stays_database_only():
    routing = route_query('数据库里有多少客户？', allow_llm=False)

    assert routing['route'] == 'DATABASE_ONLY'
    assert routing['required_tools'] == ['database_query']


def test_explicit_document_criteria_applied_to_database_routes_cross_source():
    routing = route_query('用手册里的标准检查数据库客户记录', allow_llm=False)

    assert routing['route'] == 'CROSS_SOURCE'
    assert routing['required_tools'] == ['database_query', 'document_search']


def test_document_question_about_how_to_check_database_stays_document_only():
    routing = route_query('文档里讲了如何检查数据库客户记录吗？', allow_llm=False)

    assert routing['route'] == 'DOCUMENT_ONLY'
    assert routing['required_tools'] == ['document_search']


@pytest.mark.parametrize('question', [
    '这几篇讲的是什么？',
    '这三篇分别讲什么？',
    '请总结这些材料',
    '选中的资料各有什么观点？',
    '这两份各自介绍了什么？',
])
def test_selected_material_references_route_to_document_search(question):
    routing = route_query(question, selected_document_count=3, allow_llm=False)

    assert routing['route'] == 'DOCUMENT_ONLY'
    assert [step.tool for step in create_plan(question, routing).steps] == ['document_search']


def test_selected_material_reference_without_selection_still_needs_clarification():
    assert route_query('这几篇讲的是什么？', allow_llm=False)['route'] == 'CLARIFICATION_REQUIRED'


def test_selected_materials_do_not_redirect_database_or_cross_source_questions():
    assert route_query('数据库里有多少客户？', selected_document_count=3,
                       allow_llm=False)['route'] == 'DATABASE_ONLY'
    assert route_query('数据库客户数与这几篇材料中的数字是否一致？',
                       selected_document_count=3, allow_llm=False)['route'] == 'CROSS_SOURCE'

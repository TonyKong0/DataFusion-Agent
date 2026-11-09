import pytest

from app.agent.tools.document_tool import document_search
from app.core.errors import AppError
from app.services.multitable_service import is_multitable_intent
from app.schema.candidate_retriever import retrieve_candidates
from app.schema.schema_linker import link_schema
from tests.test_schema_phase24 import linked_schema
from app.agent.service import query as agent_query


def test_sales_quantity_genre_requires_multitable_path():
    assert is_multitable_intent('销售数量最多的音乐类型是什么？')


def test_sales_quantity_genre_links_real_tables(linked_schema):
    question = '销售数量最多的音乐类型是什么？'
    linked = link_schema(question, [], retrieve_candidates(question, [], linked_schema), linked_schema)
    assert set(linked['selected_tables']) == {'genre', 'track', 'invoiceline'}
    assert 'invoiceline.Quantity' in linked['selected_columns']


def test_explicit_no_pdf_does_not_silently_select_library_document():
    with pytest.raises(AppError) as error:
        document_search('这份文档讲什么？', {'document_id': ''})
    assert error.value.code == 'DOCUMENT_SELECTION_REQUIRED'


def test_explicit_no_material_gives_clear_agent_answer():
    result = agent_query('文档讲什么？', document_id='', allow_router_llm=False)
    assert '材料' in result['answer']
    assert result['tool_results']['step_1']['error']['code'] == 'DOCUMENT_SELECTION_REQUIRED'

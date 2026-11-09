"""Offline V5 orchestration benchmark; does not claim live model answer accuracy."""
import pytest
from app.agent.router import route_query
from app.agent.planner import create_plan

DB_ENTITIES = ('客户', '员工', '订单', '歌曲', '专辑', '音乐类型', '艺术家', '曲目', '发票', '歌手')
DOC_TOPICS = ('摘要', '作者', '背景', '结论', '第一章', '目录', '目的', '方法', '术语', '公式')
DB_CASES = ([f'数据库里有多少{item}？' for item in DB_ENTITIES]
            + [f'列出数据库里的{item}。' for item in DB_ENTITIES]
            + [f'数据库里{item}的数量是多少？' for item in DB_ENTITIES])
DOC_CASES = ([f'文档中的{item}是什么？' for item in DOC_TOPICS]
             + [f'请概括文档里的{item}。' for item in DOC_TOPICS]
             + [f'文档如何解释{item}？' for item in DOC_TOPICS])
DOC_DB = [f'文档规定的{item}是多少，数据库里有多少订单超过这个值？'
          for item in ('审核阈值', '金额上限', '预算值', '目标值', '单笔限额', '基准值', '参考值',
                       '风险值', '触发值', '标准值', '告警值', '合同限额', '审批线', '报销上限', '采购上限')]
DB_DOC = [f'数据库中销量最高的{item}是什么，文档里如何描述它？'
          for item in ('音乐类型', '歌曲', '专辑', '曲目', '流派', '艺术家', '类型', '歌手',
                       '作品', '唱片', '曲风', '歌曲类型', '音乐流派', '热门曲目', '畅销专辑')]
PARALLEL = [f'数据库里有多少{item}，文档里记录了多少？' for item in DB_ENTITIES]
FORMULA = [f'根据文档中的公式计算数据库{item}增长率？'
           for item in ('销售额', '订单', '客户', '销量', '购买金额')]
CLARIFY = ['帮我看看。', '这是什么意思？', '再详细一点。', '还有别的吗？', '请继续。']


@pytest.mark.parametrize('question', DB_CASES)
def test_30_database_regression_routes(question):
    routing = route_query(question, allow_llm=False)
    assert routing['route'] == 'DATABASE_ONLY'
    assert [step.tool for step in create_plan(question, routing).steps] == ['database_query']


@pytest.mark.parametrize('question', DOC_CASES)
def test_30_document_regression_routes(question):
    routing = route_query(question, allow_llm=False)
    assert routing['route'] == 'DOCUMENT_ONLY'
    assert [step.tool for step in create_plan(question, routing).steps] == ['document_search']


@pytest.mark.parametrize('question,first,dependent',
    [(q, 'document_search', True) for q in DOC_DB]
    + [(q, 'database_query', True) for q in DB_DOC]
    + [(q, 'database_query', False) for q in PARALLEL]
    + [(q, 'document_search', True) for q in FORMULA])
def test_45_cross_source_route_and_plan(question, first, dependent):
    routing = route_query(question, allow_llm=False)
    assert routing['route'] == 'CROSS_SOURCE'
    plan = create_plan(question, routing)
    assert plan.steps[0].tool == first
    assert bool(plan.steps[1].depends_on) == dependent
    assert {plan.steps[0].tool, plan.steps[1].tool} == {'database_query', 'document_search'}
    if question in FORMULA:
        assert plan.steps[-1].tool == 'formula_calculate'


@pytest.mark.parametrize('question', CLARIFY)
def test_5_clarification_routes(question):
    routing = route_query(question, allow_llm=False)
    assert routing['route'] == 'CLARIFICATION_REQUIRED'
    assert [step.tool for step in create_plan(question, routing).steps] == ['clarification']

import pytest
from app.agent.router import route_query
from app.agent.planner import create_plan
from app.agent.plan_models import ExecutionPlan, PlanStep
from app.agent.plan_validator import validate_plan
from app.core.errors import AppError


def test_document_to_database_dependency():
    q = '文档规定审核阈值是多少，数据库里有多少订单超过这个值？'
    plan = create_plan(q, route_query(q, allow_llm=False))
    assert [s.tool for s in plan.steps] == ['document_search', 'database_query']
    assert plan.steps[1].inputs_from['threshold'] == 'step_1.data.extracted_number'


def test_database_to_document_dependency():
    q = '数据库中销量最高的音乐类型，在文档里怎么定义它？'
    plan = create_plan(q, route_query(q, allow_llm=False))
    assert [s.tool for s in plan.steps] == ['database_query', 'document_search']
    assert plan.steps[1].depends_on == ['step_1']


def test_explicit_comparison_queries_each_source_separately():
    q = '文档中的审核阈值和数据库中的审核阈值是否一致？'
    plan = create_plan(q, route_query(q, allow_llm=False))
    assert [step.tool for step in plan.steps] == ['document_search', 'database_query']
    assert '是否一致' not in plan.steps[0].instruction
    assert not plan.steps[1].depends_on


@pytest.mark.parametrize('bad_steps', [
    [PlanStep('step_1', 'invented_tool', 'x')],
    [PlanStep('step_1', 'database_query', 'x', depends_on=['step_2'])],
    [PlanStep('step_1', 'database_query', 'x'), PlanStep('step_2', 'document_search', 'x', inputs_from={'v': 'step_1.data.value'})],
    [PlanStep(f'step_{i}', 'database_query', 'x') for i in range(1, 7)],
])
def test_invalid_plan_rejected(bad_steps):
    with pytest.raises(AppError):
        validate_plan(ExecutionPlan('p', 'q', 'CROSS_SOURCE', bad_steps))


DOC_FIRST = [
    f'文档规定的{topic}是多少，数据库里有多少订单超过这个值？'
    for topic in ('审核阈值', '金额上限', '预算值', '目标值', '单笔限额', '基准值', '参考值', '风险值', '触发值', '标准值')]
DB_FIRST = [
    f'数据库中销量最高的{item}是什么，文档里如何描述它？'
    for item in ('音乐类型', '歌曲', '专辑', '曲目', '流派', '艺术家', '类型', '歌手', '作品', '唱片')]
PARALLEL = [
    f'数据库里有多少{item}，文档里记录了多少？'
    for item in ('客户', '员工', '订单', '歌曲', '专辑')]
FORMULA = [
    f'根据文档中的公式计算数据库{item}增长率？'
    for item in ('销售额', '订单', '客户', '销量', '购买金额')]


@pytest.mark.parametrize('question,first_tool,dependent',
    [(q, 'document_search', True) for q in DOC_FIRST] +
    [(q, 'database_query', True) for q in DB_FIRST] +
    [(q, 'database_query', False) for q in PARALLEL] +
    [(q, 'document_search', True) for q in FORMULA])
def test_planner_30_cases(question, first_tool, dependent):
    routing = route_query(question, allow_llm=False)
    assert routing['route'] == 'CROSS_SOURCE'
    plan = create_plan(question, routing)
    assert plan.steps[0].tool == first_tool
    assert bool(plan.steps[1].depends_on) == dependent
    assert set(step.tool for step in plan.steps) >= {'database_query', 'document_search'}

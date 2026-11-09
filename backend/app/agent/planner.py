"""Planning only: no SQL, retrieval, or tool execution occurs here."""
import re
from uuid import uuid4
from app.agent.plan_models import ExecutionPlan, PlanStep
from app.agent.plan_validator import validate_plan


def _clauses(question: str) -> list[str]:
    return [part.strip(' ，,？?。') for part in re.split(r'[，,；;？?。]', question) if part.strip(' ，,？?。')]


def create_plan(question: str, routing: dict) -> ExecutionPlan:
    route = routing['route']
    clauses = _clauses(question)
    if route == 'DATABASE_ONLY':
        steps = [PlanStep('step_1', 'database_query', question)]
    elif route == 'DOCUMENT_ONLY':
        steps = [PlanStep('step_1', 'document_search', question)]
    elif route == 'CLARIFICATION_REQUIRED':
        steps = [PlanStep('step_1', 'clarification', question)]
    elif route == 'CROSS_SOURCE':
        comparison = (re.search(r'文档(.+?)和数据库(.+?)(?:是否一致|相同吗|有何差异)', question)
                      or re.search(r'数据库(.+?)和文档(.+?)(?:是否一致|相同吗|有何差异)', question))
        if comparison:
            first_source = 'document_search' if question.index('文档') < question.index('数据库') else 'database_query'
            second_source = 'database_query' if first_source == 'document_search' else 'document_search'
            first_text = comparison.group(1).strip('中的配置里，,？?。')
            second_text = comparison.group(2).strip('中的配置里，,？?。')
            steps = [PlanStep('step_1', first_source, f'{"文档" if first_source == "document_search" else "数据库"}中{first_text}是多少？'),
                     PlanStep('step_2', second_source, f'{"文档" if second_source == "document_search" else "数据库"}中{second_text}是多少？')]
            return validate_plan(ExecutionPlan('plan_' + uuid4().hex, question, route, steps))
        first = clauses[0] if clauses else question
        rest = '，'.join(clauses[1:]) if len(clauses) > 1 else question
        document_first = any(token in first for token in ('文档', 'PDF', '手册', '报告', '资料', '说明书', '公式'))
        dependent = any(token in question for token in ('这个值', '该值', '它', '这个类型', '该类型', '这种', '根据', '超过', '对应'))
        if document_first:
            steps = [PlanStep('step_1', 'document_search', first + '？')]
            steps.append(PlanStep('step_2', 'database_query', rest + '？' if dependent else question,
                depends_on=['step_1'] if dependent else [],
                inputs_from={'threshold': 'step_1.data.extracted_number'} if dependent else {}))
        else:
            steps = [PlanStep('step_1', 'database_query', first + '？')]
            steps.append(PlanStep('step_2', 'document_search',
                ('查询 {topic} 在当前文档中的说明。' if dependent else rest + '？'),
                depends_on=['step_1'] if dependent else [],
                inputs_from={'topic': 'step_1.data.primary_value'} if dependent else {}))
        if 'formula_calculate' in routing.get('required_tools', []):
            steps.append(PlanStep(f'step_{len(steps)+1}', 'formula_calculate', '使用文档公式及前述结果计算',
                depends_on=[step.id for step in steps]))
    else:
        raise ValueError('unsupported route')
    return validate_plan(ExecutionPlan('plan_' + uuid4().hex, question, route, steps))

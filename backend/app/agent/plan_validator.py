import re
from app.agent.plan_models import ExecutionPlan
from app.agent.tool_registry import tool_names
from app.core.config import get_settings
from app.core.errors import AppError

REF = re.compile(r'^(step_\d+)\.data\.([a-z_]+)$')


def validate_plan(plan: ExecutionPlan) -> ExecutionPlan:
    if not 1 <= len(plan.steps) <= get_settings().max_plan_steps:
        raise AppError('INVALID_PLAN', '计划步骤数量超限', 422)
    seen = set()
    for index, step in enumerate(plan.steps, 1):
        if step.id != f'step_{index}' or step.id in seen or step.tool not in tool_names():
            raise AppError('INVALID_PLAN', '计划包含未知步骤或工具', 422)
        if not step.instruction.strip() or len(step.instruction) > 2000:
            raise AppError('INVALID_PLAN', '步骤指令不合法', 422)
        if any(dep not in seen for dep in step.depends_on):
            raise AppError('INVALID_PLAN', '步骤依赖必须指向先前步骤', 422)
        for reference in step.inputs_from.values():
            matched = REF.fullmatch(reference)
            if not matched or matched.group(1) not in step.depends_on:
                raise AppError('INVALID_PLAN', '参数引用不合法', 422)
        seen.add(step.id)
    return plan

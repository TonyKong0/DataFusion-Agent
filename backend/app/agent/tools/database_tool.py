from app.agent.models import ToolResult
from app.services.nl2sql_service import query


def database_query(question: str, context: dict) -> ToolResult:
    from app.services.question_provenance import preserve_question
    original = context.get('original_question') or question
    result = preserve_question(query(question, original_question=original), original, question)
    if result.get('need_clarification'):
        return ToolResult('database_query', False, data=result,
            error={'code': 'NEED_CLARIFICATION', 'message': result.get('answer', '请补充问题')})
    return ToolResult('database_query', True, data=result)

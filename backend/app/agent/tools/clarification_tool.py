from app.agent.models import ToolResult
from app.semantic.clarification_manager import create_clarification


def clarification(question: str, context: dict) -> ToolResult:
    validation = context.get('validation') or {
        'missing': [], 'ambiguities': [], 'unsupported': ['cross_source_uncertain'],
        'conflicts': [], 'error': None, 'low_confidence': False}
    prompt = create_clarification(question, validation)
    return ToolResult('clarification', True, data=prompt)

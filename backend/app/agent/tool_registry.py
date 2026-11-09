from time import perf_counter
from typing import Callable
from app.agent.models import ToolResult
from app.core.errors import AppError
from app.agent.tools.database_tool import database_query
from app.agent.tools.document_tool import document_search
from app.agent.tools.formula_tool import formula_calculate
from app.agent.tools.clarification_tool import clarification
from app.agent.tools.multimodal_tools import (multi_document_search, document_compare,
    table_query, chart_analyze, image_query)

Tool = Callable[[str, dict], ToolResult]
_TOOLS: dict[str, Tool] = {
    'database_query': database_query,
    'document_search': document_search,
    'formula_calculate': formula_calculate,
    'clarification': clarification,
    'multi_document_search': multi_document_search,
    'document_compare': document_compare,
    'table_query': table_query,
    'chart_analyze': chart_analyze,
    'image_query': image_query,
}


def tool_names() -> tuple[str, ...]:
    return tuple(_TOOLS)


def call_tool(name: str, question: str, context: dict | None = None) -> ToolResult:
    if name not in _TOOLS:
        raise AppError('UNKNOWN_TOOL', '工具未注册', 422)
    started = perf_counter()
    try:
        result = _TOOLS[name](question, context or {})
        if not isinstance(result, ToolResult) or result.tool != name:
            raise AppError('INVALID_TOOL_RESULT', '工具返回格式不合法', 500)
    except AppError as error:
        result = ToolResult(name, False,
            data={'trace': getattr(error, 'trace', [])},
            error={'code': error.code, 'message': error.message})
    result.latency_ms = round((perf_counter() - started) * 1000)
    return result

from app.agent.models import ToolResult
from app.core.errors import AppError
from app.document.multi_doc.retriever import query as multi_query
from app.document.versioning.comparator import compare
from app.document.table.qa import query_table
from app.document.chart.analyzer import query_chart
from app.document.image.image_qa import query_image


def _one(context: dict) -> str:
    ids = list(dict.fromkeys(context.get('document_ids') or []))
    if len(ids) != 1:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '表格、图表或图片问答请选择一份材料', 422)
    return ids[0]


def multi_document_search(question: str, context: dict) -> ToolResult:
    return ToolResult('multi_document_search', True, data=multi_query(context.get('document_ids') or [], question))


def document_compare(question: str, context: dict) -> ToolResult:
    ids = list(dict.fromkeys(context.get('document_ids') or []))
    if len(ids) != 2:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '版本对比请选择旧版和新版两份材料', 422)
    return ToolResult('document_compare', True, data=compare(ids[0], ids[1]))


def table_query(question: str, context: dict) -> ToolResult:
    return ToolResult('table_query', True, data=query_table(_one(context), question))


def chart_analyze(question: str, context: dict) -> ToolResult:
    return ToolResult('chart_analyze', True, data=query_chart(_one(context), question))


def image_query(question: str, context: dict) -> ToolResult:
    return ToolResult('image_query', True, data=query_image(_one(context), question))

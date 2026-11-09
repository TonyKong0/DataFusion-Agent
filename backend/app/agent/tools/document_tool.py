from app.agent.models import ToolResult
from app.core.errors import AppError
from app.services.document_service import list_documents
from app.services.rag_service import query_documents


def document_search(question: str, context: dict) -> ToolResult:
    ids = list(dict.fromkeys(context.get('document_ids') or []))
    document_id = context.get('document_id')
    if not ids and document_id:
        ids = [document_id]
    if not ids and (document_id == '' or 'document_ids' in context):
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '当前未选择材料；请先选择已索引材料', 422)
    if not ids:
        documents = [item for item in list_documents() if item.get('status') == 'indexed']
        if len(documents) != 1:
            raise AppError('DOCUMENT_SELECTION_REQUIRED', '请先选择 1–10 份已索引材料', 422)
        ids = [documents[0]['document_id']]
    if len(ids) > 10:
        raise AppError('DOCUMENT_SELECTION_LIMIT', '每轮最多选择 10 份材料', 422)
    result = query_documents(ids, question, min(int(context.get('top_k', 5)), 10))
    return ToolResult('document_search', True, data=result)

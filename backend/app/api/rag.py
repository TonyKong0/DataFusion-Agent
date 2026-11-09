from fastapi import APIRouter, Request
from app.schemas.rag import RagRequest
from app.services.rag_service import query, query_documents
from app.core.errors import AppError
from app.core.logging import log_event

router = APIRouter(prefix='/rag', tags=['rag'])


@router.post('/query')
def ask(payload: RagRequest, request: Request) -> dict:
    log_event(request_id=request.state.request_id, module='rag', question=payload.question)
    if payload.document_ids is not None:
        ids = list(dict.fromkeys(payload.document_ids))
        if payload.document_id and ids != [payload.document_id]:
            raise AppError('DOCUMENT_RANGE_CONFLICT',
                           'document_id 与 document_ids 必须表示同一个单文档范围', 422)
        return query_documents(ids, payload.question, payload.top_k)
    if payload.document_id:
        return query(payload.document_id, payload.question, payload.top_k)
    return query_documents([], payload.question, payload.top_k)

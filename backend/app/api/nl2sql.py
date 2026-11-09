from fastapi import APIRouter, Request
from app.schemas.nl2sql import QueryRequest
from app.services.nl2sql_service import query
from app.core.logging import log_event

router = APIRouter(prefix='/nl2sql', tags=['nl2sql'])


@router.post('/query')
def ask(payload: QueryRequest, request: Request) -> dict:
    log_event(request_id=request.state.request_id, module='nl2sql', question=payload.question)
    return query(payload.question)

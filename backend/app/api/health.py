from fastapi import APIRouter
from pydantic import BaseModel
from app.db.mysql import database_status
from app.core.errors import AppError
from app.core.version import APP_VERSION
from app.llm.deepseek_client import is_reachable
from app.services.document_service import list_documents

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    mysql: bool
    llm: bool
    vector_store: bool
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report live MySQL connectivity and current service readiness."""
    try:
        database_status()
        mysql_ready = True
    except AppError:
        mysql_ready = False
    from app.services.vector_store import ready
    vector_ready = any(ready(document['document_id']) for document in list_documents())
    return HealthResponse(status="ok", mysql=mysql_ready, llm=is_reachable(),
                          vector_store=vector_ready, version=APP_VERSION)

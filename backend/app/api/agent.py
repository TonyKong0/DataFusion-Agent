from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from app.agent.service import query
from app.semantic.clarification_manager import resolve_clarification

router = APIRouter(prefix='/agent', tags=['agent'])


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    document_ids: list[str] | None = None
    formula_id: str | None = None

    @field_validator('question')
    @classmethod
    def trim_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('empty question')
        return value


@router.post('/query')
def ask(payload: AgentRequest) -> dict:
    return query(payload.question, payload.document_id, payload.formula_id,
                 document_ids=payload.document_ids)


class AgentClarifyRequest(BaseModel):
    session_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    document_ids: list[str] | None = None
    formula_id: str | None = None


@router.post('/clarify')
def clarify(payload: AgentClarifyRequest) -> dict:
    resolved = resolve_clarification(payload.session_id, payload.answer)
    if resolved.get('cancelled'):
        return {'success': True, 'answer': '已取消本次查询。', 'cancelled': True}
    return query(resolved['question'], payload.document_id, payload.formula_id,
                 document_ids=payload.document_ids)

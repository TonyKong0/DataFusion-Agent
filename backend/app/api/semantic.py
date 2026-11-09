from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.semantic.clarification_manager import resolve_clarification
from app.services.nl2sql_service import query


router = APIRouter(prefix='/semantic', tags=['semantic'])


class ClarifyRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=200)


@router.post('/clarify')
def clarify(payload: ClarifyRequest) -> dict:
    resolved = resolve_clarification(payload.session_id, payload.answer)
    if resolved['cancelled']:
        return {'success': True, 'question': resolved['question'], 'need_clarification': False,
                'answer': '已取消本次查询。', 'sql': None, 'table': None,
                'columns': [], 'rows': [], 'row_count': 0, 'sources': [], 'trace': []}
    return query(resolved['question'], confirmed=resolved['confirmed'],
                 clarification_completed=True, original_question=resolved['original_question'])

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schema.metadata_store import get_metadata, refresh_metadata
from app.schema.candidate_retriever import retrieve_candidates
from app.schema.schema_linker import link_schema


router = APIRouter(prefix='/schema', tags=['schema'])


@router.post('/refresh')
def refresh() -> dict:
    return {'success': True, 'schema': refresh_metadata().model_dump()}


class LinkRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    elements: list[dict] = Field(default_factory=list, max_length=30)


@router.post('/link')
def link(payload: LinkRequest) -> dict:
    metadata = get_metadata()
    candidates = retrieve_candidates(payload.question, payload.elements, metadata)
    selection = link_schema(payload.question, payload.elements, candidates, metadata)
    return {'success': True, 'question': payload.question,
            'candidate_tables': candidates['candidate_tables'],
            'candidate_columns': candidates['candidate_columns'], **selection}

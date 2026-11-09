from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.agent.multimodal_service import query
from app.document.table.extractor import extract_tables
from app.document.chart.analyzer import extract_charts
from app.document.image.image_qa import extract_images

router = APIRouter(prefix='/multimodal', tags=['multimodal'])


class MultimodalRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list)


@router.post('/query')
def ask(payload: MultimodalRequest) -> dict:
    return query(payload.question.strip(), payload.document_ids)


@router.get('/documents/{document_id}/assets')
def assets(document_id: str) -> dict:
    images = [{key: value for key, value in image.items() if key != '_bytes'}
              for image in extract_images(document_id)]
    return {'success': True, 'tables': extract_tables(document_id),
            'charts': extract_charts(document_id), 'images': images}

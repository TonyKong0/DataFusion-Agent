from fastapi import APIRouter
from app.db.mysql import database_status
from app.db.schema_loader import load_schema

router = APIRouter(prefix='/database', tags=['database'])


@router.get('/status')
def status() -> dict:
    return {'success': True, **database_status()}


@router.get('/schema')
def schema() -> dict:
    return {'success': True, 'tables': load_schema()}

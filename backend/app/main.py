from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.database import router as database_router
from app.api.nl2sql import router as nl2sql_router
from app.api.documents import router as documents_router
from app.api.rag import router as rag_router
from app.api.semantic import router as semantic_router
from app.api.schema import router as schema_router
from app.api.agent import router as agent_router
from app.api.evaluation import router as evaluation_router
from app.api.multimodal import router as multimodal_router
from app.api.conversations import router as conversations_router
from app.core.errors import AppError
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
import time
import uuid
from app.core.logging import log_event
from app.core.version import APP_VERSION
from contextlib import asynccontextmanager
from app.schema.metadata_store import get_metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        snapshot = get_metadata()
        log_event(module='schema', event='loaded', database=snapshot.database,
                  tables=len(snapshot.tables))
    except Exception as error:
        # Keep existing V1/V2 routes available if MySQL is temporarily offline.
        log_event(module='schema', event='load_failed', error=type(error).__name__)
    yield

app = FastAPI(title="DataFusion Agent", version=APP_VERSION, lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(database_router, prefix='/api')
app.include_router(nl2sql_router, prefix='/api')
app.include_router(documents_router, prefix='/api')
app.include_router(rag_router, prefix='/api')
app.include_router(semantic_router, prefix='/api')
app.include_router(schema_router, prefix='/api')
app.include_router(agent_router, prefix='/api')
app.include_router(evaluation_router, prefix='/api')
app.include_router(multimodal_router, prefix='/api')
app.include_router(conversations_router, prefix='/api')


@app.middleware('http')
async def request_log(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    log_event(request_id=request.state.request_id, module=request.url.path,
              latency_ms=round((time.perf_counter()-started)*1000),
              success=response.status_code < 400, error=response.status_code if response.status_code >= 400 else None)
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={'success': False, 'error': {'code': exc.code, 'message': exc.message}, 'trace': getattr(exc, 'trace', [])})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={'success': False, 'error': {'code': 'INVALID_REQUEST', 'message': '请求参数不合法'}})


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={'success': False, 'error': {'code': 'HTTP_ERROR', 'message': str(exc.detail)}})


@app.exception_handler(Exception)
async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={'success': False, 'error': {'code': 'INTERNAL_ERROR', 'message': '服务处理失败'}})

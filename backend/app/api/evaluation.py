"""Read-only access to measured regression and historical evaluation artifacts."""
import json
import ipaddress
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from app.core.config import BACKEND_DIR
from app.services import evaluation_workbench as workbench

router = APIRouter(prefix='/evaluation', tags=['evaluation'])
ROOT = BACKEND_DIR.parent
REPORT_PATH = ROOT / 'reports/test_summary.json'
DOCS = ROOT / 'docs'


class WorkbenchJobRequest(BaseModel):
    action: Literal['download', 'preview', 'import', 'smoke',
                    'retail_evaluation', 'qa_evaluation',
                    'agent_offline_evaluation', 'multimodal_offline_evaluation',
                    'ohr_evaluation', 'conversation_memory_evaluation']
    repeat: int = Field(default=3, ge=1, le=20)
    max_api_requests: int | None = Field(default=None, ge=1, le=2000)
    context_limit_tokens: int | None = Field(default=None, ge=1000, le=50000)

    @model_validator(mode='after')
    def require_live_request_cap(self):
        if self.action in {'retail_evaluation', 'qa_evaluation', 'ohr_evaluation',
                           'conversation_memory_evaluation'} \
                and self.max_api_requests is None:
            raise ValueError('真实评测必须设置 API 请求上限')
        if self.action == 'conversation_memory_evaluation' and self.context_limit_tokens is None:
            raise ValueError('连续对话评测必须设置上下文预算上限')
        return self


def _require_loopback(request: Request):
    client_host = request.client.host if request.client else ''
    try:
        loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise HTTPException(status_code=403, detail='本机评测操作只允许从本机访问')


@router.get('/workbench')
def workbench_status() -> dict:
    return {'success': True, **workbench.status()}


@router.post('/workbench/jobs', status_code=status.HTTP_202_ACCEPTED)
def start_workbench_job(payload: WorkbenchJobRequest, request: Request) -> dict:
    _require_loopback(request)
    try:
        options = {'repeat': payload.repeat, 'max_api_requests': payload.max_api_requests}
        if payload.context_limit_tokens is not None:
            options['context_limit_tokens'] = payload.context_limit_tokens
        job = workbench.start(payload.action, **options)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return {'success': True, **job}


@router.get('/workbench/jobs/{job_id}')
def workbench_job_status(job_id: str) -> dict:
    job = workbench.job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='评测任务不存在或后端已重启')
    return {'success': True, **job}


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _version_results() -> list[dict]:
    results = []
    semantic = _read_json(DOCS / 'evaluation_v2_results.json') or {}
    for version in ('v1', 'v2'):
        row = (semantic.get('summary') or {}).get(version)
        if isinstance(row, dict) and row.get('cases'):
            results.append({'version': version.upper(), 'task': '单表问数', 'sample_count': row['cases'],
                            'metric': '用例正确率', 'value': row.get('accuracy'),
                            'average_latency_ms': row.get('avg_latency_ms'),
                            'source': 'docs/evaluation_v2_results.json', 'scope': '同一组 6 条问题，可在 V1/V2 间比较'})
    multi = _read_json(DOCS / 'evaluation_multitable_v3_live.json') or {}
    if multi.get('mode') == 'live' and multi.get('cases') and isinstance(multi.get('metrics'), dict):
        results.append({'version': 'V3', 'task': '多表问数', 'sample_count': multi['cases'],
                        'metric': '结果正确率', 'value': multi['metrics'].get('result_correct'),
                        'average_latency_ms': None, 'source': 'docs/evaluation_multitable_v3_live.json',
                        'scope': '50 条多表题；不能与 V1/V2 六题直接比较'})
    document = _read_json(DOCS / 'evaluation_document_v4_live.json') or {}
    rag = (document.get('rag_live') or {})
    rag_metrics = (rag.get('metrics') or {}).get('v4') or {}
    if rag.get('cases') and rag_metrics:
        results.append({'version': 'V4', 'task': '受控 PDF RAG', 'sample_count': len(rag['cases']),
                        'metric': '答案正确率', 'value': rag_metrics.get('answer_accuracy'),
                        'average_latency_ms': rag_metrics.get('avg_retrieval_answer_latency_ms'),
                        'source': 'docs/evaluation_document_v4_live.json',
                        'scope': '10 份受控英文文档；不是未知真实文档泛化准确率'})
    return results


@router.get('/summary')
def summary() -> dict:
    report = _read_json(REPORT_PATH)
    versions = _version_results()
    if report:
        route_cases = next((row for row in report.get('modules', [])
                            if row.get('module') == 'tests.test_agent_phase50_eval'), None)
        if route_cases:
            versions.append({'version': 'V5', 'task': '离线路由与规划',
                             'sample_count': route_cases['total'], 'metric': '回归断言通过率',
                             'value': route_cases['passed'] / route_cases['total'] if route_cases['total'] else None,
                             'average_latency_ms': None, 'source': 'reports/test_summary.json',
                             'scope': '模拟/离线测试；不是跨源答案准确率'})
    failure_cases = _read_json(DOCS / 'failure_cases_phase55.json') or {}
    return {'success': True, 'report_available': report is not None, 'report': report,
            'version_comparison': versions, 'failure_cases': failure_cases.get('cases', [])}

"""Allowlisted local jobs for preparing and evaluating the retail benchmark."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import zipfile

import pymysql

from app.core.config import BACKEND_DIR, get_settings

DATASET_PATH = BACKEND_DIR / 'data' / 'benchmarks' / 'online-retail-ii.xlsx'
OHR_PDF_ZIP_PATH = BACKEND_DIR / 'data' / 'benchmarks' / 'ohr-bench-v2-pdfs.zip'
MEMORY_DEMO_PDF_PATH = BACKEND_DIR.parent / 'docs' / 'demo.pdf'
DATASET_SIZE = 45_622_278
DATASET_SHA256 = 'bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980'
DATABASES = {'retail_bench_1k': 1000, 'retail_bench_10k': 10000}
REPORT_DIR = BACKEND_DIR / 'data' / 'evaluation'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class EvaluationWorkbench:
    def __init__(self):
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='evaluation-workbench')
        self._job: dict | None = None
        self._preview_hash: str | None = None
        self._dataset_cache: tuple[int, int, dict] | None = None

    def _dataset_status(self) -> dict:
        try:
            stat = DATASET_PATH.stat()
        except OSError:
            return {'downloaded': False, 'checksum_verified': False, 'size_bytes': 0,
                    'expected_size_bytes': DATASET_SIZE, 'sha256': None,
                    'expected_sha256': DATASET_SHA256}
        cached = self._dataset_cache
        if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return deepcopy(cached[2])
        actual_hash = _sha256(DATASET_PATH) if stat.st_size == DATASET_SIZE else None
        result = {'downloaded': True, 'checksum_verified': actual_hash == DATASET_SHA256,
                  'size_bytes': stat.st_size, 'expected_size_bytes': DATASET_SIZE,
                  'sha256': actual_hash, 'expected_sha256': DATASET_SHA256}
        self._dataset_cache = (stat.st_size, stat.st_mtime_ns, result)
        return deepcopy(result)

    @staticmethod
    def _ohr_dataset_status() -> dict:
        try:
            size_bytes = OHR_PDF_ZIP_PATH.stat().st_size
        except OSError:
            return {'available': False, 'size_bytes': 0,
                    'path': 'backend/data/benchmarks/ohr-bench-v2-pdfs.zip'}
        is_archive = size_bytes > 0 and zipfile.is_zipfile(OHR_PDF_ZIP_PATH)
        return {'available': is_archive, 'size_bytes': size_bytes,
                'path': 'backend/data/benchmarks/ohr-bench-v2-pdfs.zip'}

    def _database_status(self) -> dict:
        settings = get_settings()
        schemas = {name: {'expected_rows': expected, 'exists': False,
                          'table_exists': False, 'rows': None}
                   for name, expected in DATABASES.items()}
        if not settings.mysql_user:
            return {'connected': False, 'ready': False, 'schemas': schemas,
                    'error': '未配置 MySQL 用户'}
        try:
            connection = pymysql.connect(host=settings.mysql_host, port=settings.mysql_port,
                user=settings.mysql_user, password=settings.mysql_password.get_secret_value(),
                charset='utf8mb4', connect_timeout=3, read_timeout=5)
            try:
                with connection.cursor() as cursor:
                    for name in DATABASES:
                        cursor.execute('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',
                                       (name,))
                        exists = bool(cursor.fetchone()[0])
                        schemas[name]['exists'] = exists
                        if not exists:
                            continue
                        cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES '
                                       'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
                                       (name, 'retail_transaction'))
                        schemas[name]['table_exists'] = bool(cursor.fetchone()[0])
                        if schemas[name]['table_exists']:
                            cursor.execute(f'SELECT COUNT(*) FROM `{name}`.retail_transaction')
                            schemas[name]['rows'] = int(cursor.fetchone()[0])
            finally:
                connection.close()
            ready = all(schemas[name]['table_exists'] and schemas[name]['rows'] == expected
                        for name, expected in DATABASES.items())
            return {'connected': True, 'ready': ready, 'schemas': schemas, 'error': None}
        except Exception:
            return {'connected': False, 'ready': False, 'schemas': schemas,
                    'error': '无法连接本机 MySQL，请检查服务和 backend/.env'}

    def status(self) -> dict:
        settings = get_settings()
        with self._lock:
            job = deepcopy(self._job)
            preview_hash = self._preview_hash
        dataset = self._dataset_status()
        local_embedding_model = BACKEND_DIR / 'data' / 'models' / 'bge-m3'
        cached_embedding_model = Path(settings.embedding_cache_dir) / 'models--BAAI--bge-m3'
        embedding_weights_available = (
            any((local_embedding_model / filename).is_file()
                for filename in ('pytorch_model.bin', 'model.safetensors'))
            or cached_embedding_model.is_dir())
        try:
            from app.services.document_service import list_documents
            indexed_documents = [item for item in list_documents() if item.get('status') == 'indexed']
        except Exception:
            indexed_documents = []
        database = self._database_status()
        return {'dataset': dataset, 'database': database,
                'ohr_benchmark': self._ohr_dataset_status(),
                'model': {'configured': bool(settings.deepseek_api_key.get_secret_value()),
                          'name': settings.deepseek_model},
                'local_embedding_model_available': embedding_weights_available,
                'qa_evaluation_ready': len(indexed_documents) == 1,
                'qa_indexed_documents': len(indexed_documents),
                'memory_evaluation_ready': (MEMORY_DEMO_PDF_PATH.is_file()
                    and bool(settings.deepseek_api_key.get_secret_value())
                    and embedding_weights_available
                    and settings.mysql_database.casefold() == 'chinook'
                    and database.get('connected') is True),
                'memory_evaluation_fixture': 'docs/demo.pdf' if MEMORY_DEMO_PDF_PATH.is_file() else None,
                'preview_ready': bool(dataset['checksum_verified'] and preview_hash == dataset['sha256']),
                'job': job}

    def job_status(self, job_id: str) -> dict | None:
        with self._lock:
            if not self._job or self._job['job_id'] != job_id:
                return None
            return deepcopy(self._job)

    def _command(self, action: str, repeat: int, max_api_requests: int | None,
                 context_limit_tokens: int | None = None) -> tuple[list[str], str]:
        python = sys.executable
        scripts = BACKEND_DIR / 'scripts'
        evaluation_reports = REPORT_DIR
        if action == 'download':
            return [python, str(scripts / 'download_retail_benchmark.py')], '下载并验证 Online Retail II 数据'
        if action in {'preview', 'import'}:
            command = [python, str(scripts / 'prepare_retail_benchmark.py'),
                       '--source', str(DATASET_PATH)]
            if action == 'import':
                command.append('--apply')
            return command, '扫描并生成抽样预览' if action == 'preview' else '导入 1k / 10k MySQL 基准库'
        if action == 'smoke':
            return [python, str(scripts / 'smoke_retail_benchmark.py')], '执行两个规模的只读 SQL 冒烟检查'
        if action == 'retail_evaluation':
            return [python, str(scripts / 'evaluate_retail_benchmark.py'), '--live',
                    '--repeat', str(repeat), '--max-api-requests', str(max_api_requests),
                    '--output', str(evaluation_reports / 'retail-benchmark.json')], '测量 retail 1k / 10k 基准'
        if action == 'qa_evaluation':
            return [python, str(scripts / 'evaluate.py'), '--live',
                    '--max-api-requests', str(max_api_requests),
                    '--output', str(evaluation_reports / 'nl2sql-rag.json')], '运行 10 题 NL2SQL + 10 题材料问答'
        if action == 'agent_offline_evaluation':
            command = [python, str(scripts / 'evaluate_agent_v5.py')]
            if max_api_requests:
                command += ['--live', '--max-api-requests', str(max_api_requests)]
            command += ['--output', str(evaluation_reports /
                                       ('agent-live.json' if max_api_requests else 'agent-offline.json'))]
            if max_api_requests:
                return command, f'运行跨源 Agent 真实路由与工具执行评测（最多 {max_api_requests} 次 API 请求）'
            return command, '运行跨源 Agent 离线评测（110 个问题）'
        if action == 'multimodal_offline_evaluation':
            return [python, str(scripts / 'evaluate_v7_multimodal.py'),
                    '--output-dir', str(evaluation_reports / 'multimodal-offline')], \
                '运行材料与多模态离线评测（100 项）'
        if action == 'ohr_evaluation':
            return [python, str(scripts / 'evaluate_ohr_bench.py'),
                    '--pdf-zip', str(OHR_PDF_ZIP_PATH), '--live',
                    '--max-api-requests', str(max_api_requests),
                    '--output', str(evaluation_reports / 'ohr-bench.json')], \
                '运行 OHR-Bench 材料问答评测（15 题）'
        if action == 'conversation_memory_evaluation':
            return [python, str(scripts / 'evaluate_conversation_memory.py'), '--live',
                    '--max-api-requests', str(max_api_requests),
                    '--context-limit-tokens', str(context_limit_tokens),
                    '--output', str(evaluation_reports / 'conversation-memory.json')], \
                '运行数据库、材料与跨源连续五轮记忆评测（共 15 轮）'
        raise ValueError('不支持的评测操作')

    def start(self, action: str, *, repeat: int = 3,
              max_api_requests: int | None = None,
              context_limit_tokens: int | None = None) -> dict:
        if action not in {'download', 'preview', 'import', 'smoke',
                          'retail_evaluation', 'qa_evaluation',
                          'agent_offline_evaluation', 'multimodal_offline_evaluation',
                          'ohr_evaluation', 'conversation_memory_evaluation'}:
            raise ValueError('不支持的评测操作')
        if action in {'retail_evaluation', 'qa_evaluation', 'ohr_evaluation',
                      'conversation_memory_evaluation'} and not max_api_requests:
            raise ValueError('真实评测必须设置 API 请求上限')
        if action == 'conversation_memory_evaluation':
            if not context_limit_tokens or not 1000 <= context_limit_tokens <= 50000:
                raise ValueError('连续对话评测必须设置 1,000–50,000 Token 的上下文预算')
            if not self.status().get('memory_evaluation_ready'):
                raise RuntimeError('需要配置模型、Chinook 数据库和本地 BGE-M3 权重，且 docs/demo.pdf 必须存在')
        if action == 'ohr_evaluation' and not self._ohr_dataset_status()['available']:
            raise RuntimeError('缺少 OHR-Bench PDF 压缩包，请按评测说明放入 backend/data/benchmarks/ohr-bench-v2-pdfs.zip')
        if action == 'import':
            dataset = self._dataset_status()
            if not dataset['checksum_verified'] or self._preview_hash != dataset['sha256']:
                raise RuntimeError('请先下载并校验数据，再运行预览后导入')
        if action in {'preview', 'import'} and not self._dataset_status()['checksum_verified']:
            raise RuntimeError('数据文件缺失或校验失败，请先下载并验证')
        command, phase = self._command(action, repeat, max_api_requests, context_limit_tokens)
        with self._lock:
            if self._job and self._job['status'] in {'queued', 'running'}:
                raise RuntimeError('另一个评测操作正在运行，请等待完成')
            job_id = 'eval_' + uuid.uuid4().hex
            self._job = {'job_id': job_id, 'action': action, 'status': 'queued',
                         'phase': phase, 'started_at': time.time(), 'finished_at': None,
                         'exit_code': None, 'output': [], 'summary': None, 'error': None}
            self._executor.submit(self._run, job_id, command)
            return deepcopy(self._job)

    def _set_job(self, job_id: str, **changes) -> bool:
        with self._lock:
            if not self._job or self._job['job_id'] != job_id:
                return False
            self._job.update(changes)
            return True

    @staticmethod
    def _extract_summary(output: str) -> dict | None:
        decoder = json.JSONDecoder()
        summaries = []
        for position in range(len(output) - 1, -1, -1):
            if output[position] != '{':
                continue
            try:
                value, _ = decoder.raw_decode(output[position:])
                if isinstance(value, dict):
                    summaries.append(value)
            except json.JSONDecodeError:
                continue
        return max(summaries, key=lambda value: len(json.dumps(value, ensure_ascii=False)), default=None)

    @staticmethod
    def _job_outcome(return_code: int, action: str, summary: dict | None) -> tuple[str, str | None]:
        if return_code == 0:
            return 'succeeded', None
        if (action in {'retail_evaluation', 'qa_evaluation', 'ohr_evaluation'}
                and isinstance(summary, dict) and summary.get('complete') is True):
            return 'completed_with_failures', '评测已完成，部分题未通过；请查看准确率和逐题结果。'
        if action in {'retail_evaluation', 'qa_evaluation', 'ohr_evaluation'}:
            return 'failed', '评测未完整执行；请查看末尾输出，确认请求上限和运行错误。'
        return 'failed', '操作失败；请查看末尾输出并修复环境后重试'

    def _run(self, job_id: str, command: list[str]) -> None:
        self._set_job(job_id, status='running')
        output_lines: deque[str] = deque(maxlen=80)
        full_output = []
        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment['PYTHONUTF8'] = '1'
            process = subprocess.Popen(command, cwd=BACKEND_DIR, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', bufsize=1, shell=False)
            assert process.stdout is not None
            for line in process.stdout:
                value = line.rstrip()
                output_lines.append(value)
                full_output.append(value)
                self._set_job(job_id, output=list(output_lines))
            return_code = process.wait()
            text_output = '\n'.join(full_output)
            summary = self._extract_summary(text_output)
            action = self._job['action'] if self._job else ''
            if return_code == 0 and action == 'preview' and summary \
                    and summary.get('source_rows', 0) >= 10000:
                self._preview_hash = self._dataset_status()['sha256']
            status, error = self._job_outcome(return_code, action, summary)
            self._set_job(job_id, status=status,
                finished_at=time.time(), exit_code=return_code, output=list(output_lines),
                summary=summary, error=error)
        except Exception as error:
            output_lines.append(str(error))
            self._set_job(job_id, status='failed', finished_at=time.time(),
                          exit_code=None, output=list(output_lines),
                          error='本机评测任务无法启动或运行失败')


workbench = EvaluationWorkbench()


def status() -> dict:
    return workbench.status()


def start(action: str, *, repeat: int = 3, max_api_requests: int | None = None,
          context_limit_tokens: int | None = None) -> dict:
    return workbench.start(action, repeat=repeat, max_api_requests=max_api_requests,
                           context_limit_tokens=context_limit_tokens)


def job_status(job_id: str) -> dict | None:
    return workbench.job_status(job_id)

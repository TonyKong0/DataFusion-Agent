import json
import pymupdf
import re
import threading
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.core.config import BACKEND_DIR
from app.core.errors import AppError
from app.document.pipeline import process_document
from app.services.document_parser import parse_document, validate_filename
from app.services.text_splitter import split_pages
from app.document.structure.chunking import split_hierarchical
from app.document.table.extractor import extract_from_pages

DOCUMENT_DIR = BACKEND_DIR / 'data/documents'
DOCUMENT_LOCK = threading.RLock()
INDEX_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='document-index')
INDEX_JOB_LOCK = threading.RLock()
ACTIVE_INDEX_JOBS: dict[str, object] = {}
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_DOCUMENTS_PER_BATCH = 10
MAX_TOTAL_SIZE = 100 * 1024 * 1024
ACTIVE_INDEX_STATUSES = {'uploaded', 'parsing', 'chunking', 'embedding', 'persisting'}


def document_path(document_id: str) -> Path:
    if not re.fullmatch(r'doc_[a-f0-9]{32}', document_id):
        raise AppError('DOCUMENT_NOT_FOUND', '文档不存在', 404)
    return DOCUMENT_DIR / f'{document_id}.json'


def load_document(document_id: str) -> dict:
    path = document_path(document_id)
    if not path.exists():
        raise AppError('DOCUMENT_NOT_FOUND', '文档不存在', 404)
    return _with_source_metadata(json.loads(path.read_text(encoding='utf-8')))


def _with_source_metadata(document: dict) -> dict:
    """Fill source metadata omitted by documents indexed before page previews existed."""
    extension = document.get('extension') or Path(document.get('filename') or '').suffix.lower()
    if extension and not extension.startswith('.'):
        extension = f'.{extension}'
    if extension and not document.get('extension'):
        document['extension'] = extension
    if document.get('preview_available') is None:
        document['preview_available'] = (extension in {'.pdf', '.png', '.jpg', '.jpeg'}
            and (DOCUMENT_DIR / f"{document['document_id']}{extension}").is_file())
    return document


def original_file_path(document_id: str) -> tuple[Path, str]:
    """Resolve an uploaded source file using its validated stored extension."""
    document = load_document(document_id)
    extension = document.get('extension') or Path(document['filename']).suffix.lower()
    path = DOCUMENT_DIR / f'{document_id}{extension}'
    if not path.is_file():
        raise AppError('DOCUMENT_NOT_FOUND', '原始资料不存在', 404)
    return path, document['filename']


def original_pdf_path(document_id: str) -> tuple[Path, str]:
    """Backward-compatible PDF-only resolver for PDF analysis components."""
    path, filename = original_file_path(document_id)
    if path.suffix.lower() != '.pdf':
        raise AppError('PREVIEW_UNAVAILABLE', '该资料不是 PDF', 404)
    return path, filename


def render_pdf_page(document_id: str, page_number: int) -> bytes:
    """Render the cited page from the stored original PDF on demand."""
    path, _ = original_pdf_path(document_id)
    document = load_document(document_id)
    if page_number < 1 or page_number > document['pages']:
        raise AppError('PAGE_NOT_FOUND', 'PDF 页码不存在', 404)
    try:
        with pymupdf.open(path) as pdf:
            page = pdf[page_number - 1]
            scale = min(1.6, 1800 / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes('png')
    except Exception:
        raise AppError('PDF_RENDER_FAILED', 'PDF 页面预览失败', 500) from None


def render_document_page(document_id: str, page_number: int) -> bytes:
    """Render a PDF page or the single image page used as OCR evidence."""
    document = load_document(document_id)
    extension = document.get('extension') or Path(document['filename']).suffix.lower()
    if extension == '.pdf':
        return render_pdf_page(document_id, page_number)
    if extension not in {'.png', '.jpg', '.jpeg'} or page_number != 1:
        raise AppError('PREVIEW_UNAVAILABLE', '该资料格式不支持页面预览', 404)
    path, _ = original_file_path(document_id)
    try:
        with pymupdf.open(stream=path.read_bytes(), filetype=extension.lstrip('.')) as image:
            return image[0].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False).tobytes('png')
    except Exception:
        raise AppError('IMAGE_RENDER_FAILED', '图片预览失败', 500) from None


def list_documents() -> list[dict]:
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    documents = []
    for path in DOCUMENT_DIR.glob('doc_*.json'):
        document = _with_source_metadata(json.loads(path.read_text(encoding='utf-8')))
        document = _recover_orphaned_index_job(document)
        document['index_status'] = _index_status(document)
        documents.append({k: v for k, v in document.items() if k != 'content'})
    return documents


def _index_status(document: dict) -> dict:
    status = document.get('index_status')
    if isinstance(status, dict):
        return status
    current = document.get('status', 'uploaded')
    if current == 'parsed':
        current = 'uploaded'
    chunks = document.get('chunks')
    return {'job_id': None, 'status': current, 'phase': current,
            'completed_chunks': chunks if current == 'indexed' and isinstance(chunks, int) else 0,
            'total_chunks': chunks, 'percent': 100 if current == 'indexed' else None,
            'retryable': current in {'uploaded', 'failed'}, 'error': None}


def _save_document(document: dict) -> None:
    path = document_path(document['document_id'])
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _mime_type(extension: str) -> str:
    return {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.csv': 'text/csv', '.txt': 'text/plain', '.md': 'text/markdown',
        '.markdown': 'text/markdown', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    }[extension]


def _prepare_document(content: bytes, filename: str, document_id: str) -> dict:
    """Parse one material into indexable chunks while retaining PDF analysis."""
    safe_name, extension = validate_filename(filename)
    started = time.perf_counter()
    if extension == '.pdf':
        processed = process_document(content, document_id)
        pages = processed['pages']
        if not any(page.text.strip() for page in pages):
            raise AppError('PDF_NO_TEXT', '文档未提取到可索引文字')
        parsed_at = time.perf_counter()
        chunks = (split_hierarchical(pages, document_id, safe_name)
                  if 'hierarchical_chunking' in processed['complexity']['recommended_strategy']
                  else split_pages([{'page': page.page, 'text': page.text,
                                     'kind': page.metadata.get('kind', 'pdf')}
                                    for page in pages], document_id, safe_name))
        tables = [{**table, 'extension': extension, 'preview_available': True}
                  for table in extract_from_pages(pages, safe_name, document_id)]
        processing = {'metadata': processed['metadata'], 'complexity': processed['complexity'],
            'quality': processed['quality'], 'formulas': processed['formulas'], 'tables': tables,
            'tree': processed['tree'].to_dict(),
            'headings': [heading for page in pages for heading in page.headings],
            'pages': [{'page': page.page, 'metadata': page.metadata} for page in pages]}
        trace = [{'step': item['step'], 'name': item['step'], 'status': item['status'], 'duration_ms': 0}
                 for item in processed['trace']]
        trace.append({'step': 'pdf_parse', 'name': 'pdf_parse', 'status': 'success',
                      'duration_ms': round((parsed_at - started) * 1000)})
        page_count = len(pages)
    else:
        parsed = parse_document(content, safe_name)
        parsed_at = time.perf_counter()
        chunks = split_pages(parsed.pages, document_id, safe_name)
        tables = [{**table, 'document_id': document_id, 'filename': safe_name,
                   'extension': extension, 'preview_available': parsed.preview_available}
                  for table in parsed.tables]
        processing = {'tables': tables,
            'pages': [{'page': page['page'], 'locator': page.get('locator'),
                       'kind': page.get('kind')} for page in parsed.pages]}
        trace = [{'step': 'document_parse', 'name': 'document_parse', 'status': 'success',
                  'duration_ms': round((parsed_at - started) * 1000), 'format': extension}]
        page_count = len(parsed.pages)
    if not chunks:
        raise AppError('DOCUMENT_NO_TEXT', '未提取到可检索文本')
    split_at = time.perf_counter()
    trace.append({'step': 'chunk', 'name': 'chunk', 'status': 'success',
                  'duration_ms': round((split_at - parsed_at) * 1000)})
    return {'filename': safe_name, 'extension': extension, 'file_type': extension.lstrip('.'),
        'mime_type': _mime_type(extension),
        'preview_available': extension in {'.pdf', '.png', '.jpg', '.jpeg'},
        'size_bytes': len(content), 'pages': page_count, 'chunks': len(chunks),
        'content': chunks, 'processing': processing, 'trace': trace}


def _public_document(document: dict) -> dict:
    return {**{key: value for key, value in document.items() if key != 'content'},
            'index_status': _index_status(document)}


def _recover_orphaned_index_job(document: dict) -> dict:
    status = _index_status(document)
    if status.get('status') not in ACTIVE_INDEX_STATUSES:
        return document
    with INDEX_JOB_LOCK:
        active = ACTIVE_INDEX_JOBS.get(document['document_id'])
    if active is not None and not active.done():
        return document
    from app.services.vector_store import ready
    usable = ready(document['document_id'])
    status.update({'status': 'failed', 'phase': 'failed', 'retryable': True,
        'error': '索引任务已中断，请重试' if not usable else '重建任务已中断，仍在使用上一次成功的索引',
        'percent': None, 'updated_at': time.time()})
    document['status'] = 'indexed' if usable else 'failed'
    document['index_status'] = status
    _save_document(document)
    return document


def get_index_status(document_id: str) -> dict:
    return _public_document(_recover_orphaned_index_job(load_document(document_id)))


def _update_index_status(document_id: str, job_id: str, status: str, **changes) -> dict:
    with DOCUMENT_LOCK:
        document = load_document(document_id)
        current = _index_status(document)
        if current.get('job_id') not in {None, job_id} and current.get('status') in ACTIVE_INDEX_STATUSES:
            return _public_document(document)
        current.update(changes)
        current.update({'job_id': job_id, 'status': status, 'phase': status, 'updated_at': time.time()})
        from app.services.vector_store import ready
        has_index = ready(document_id)
        if status == 'indexed' or (status == 'failed' and has_index):
            document['status'] = 'indexed'
        elif not has_index:
            document['status'] = status
        document['index_status'] = current
        _save_document(document)
        return _public_document(document)


def _run_index_job(document_id: str, job_id: str) -> None:
    try:
        document = load_document(document_id)
        if not document.get('content'):
            _update_index_status(document_id, job_id, 'parsing', completed_chunks=0,
                                 total_chunks=None, percent=None, error=None, retryable=False)
            original, filename = original_file_path(document_id)
            prepared = _prepare_document(original.read_bytes(), filename, document_id)
            _update_index_status(document_id, job_id, 'chunking', completed_chunks=0,
                                 total_chunks=len(prepared['content']), percent=None,
                                 error=None, retryable=False)
            with DOCUMENT_LOCK:
                document = load_document(document_id)
                document.update(prepared)
                _save_document(document)
        total = len(document.get('content') or [])
        if not total:
            raise AppError('PDF_NO_TEXT', '文档未提取到可索引文字')
        _update_index_status(document_id, job_id, 'chunking', completed_chunks=0,
                             total_chunks=total, percent=None, error=None, retryable=False)
        _update_index_status(document_id, job_id, 'embedding', completed_chunks=0,
                             total_chunks=total, percent=None, error=None, retryable=False)
        from app.services.vector_store import build_index

        def update_embedding_progress(completed: int, total_chunks: int) -> None:
            _update_index_status(document_id, job_id, 'embedding',
                completed_chunks=completed, total_chunks=total_chunks,
                percent=min(99, int(completed * 100 / max(1, total_chunks))),
                error=None, retryable=False)

        build_index(document, progress=update_embedding_progress)
        _update_index_status(document_id, job_id, 'persisting', completed_chunks=total,
                             total_chunks=total, percent=None, error=None, retryable=False)
        with DOCUMENT_LOCK:
            document = load_document(document_id)
            trace = [step for step in document.get('trace', []) if step.get('step') != 'embedding']
            trace.append({'step': 'embedding', 'name': 'embedding', 'status': 'success'})
            document['trace'] = trace
            _save_document(document)
        _update_index_status(document_id, job_id, 'indexed', completed_chunks=total,
                             total_chunks=total, percent=100, error=None, retryable=False)
    except AppError as error:
        try:
            _update_index_status(document_id, job_id, 'failed', error=error.message,
                                 percent=None, retryable=True)
        except AppError:
            pass
    except Exception as error:
        try:
            _update_index_status(document_id, job_id, 'failed',
                error=f'索引失败（{type(error).__name__}），请检查文档、Embedding 模型和磁盘空间后重试',
                percent=None, retryable=True)
        except AppError:
            pass


def _forget_completed_index_job(document_id: str, future) -> None:
    with INDEX_JOB_LOCK:
        if ACTIVE_INDEX_JOBS.get(document_id) is future:
            ACTIVE_INDEX_JOBS.pop(document_id, None)


def start_index_job(document_id: str) -> dict:
    with INDEX_JOB_LOCK:
        document = load_document(document_id)
        active = ACTIVE_INDEX_JOBS.get(document_id)
        if active is not None and not active.done() and _index_status(document).get('status') in ACTIVE_INDEX_STATUSES:
            return _public_document(document)
        job_id = 'job_' + uuid.uuid4().hex
        _update_index_status(document_id, job_id, 'uploaded', completed_chunks=0,
                             total_chunks=len(document.get('content') or []), percent=None,
                             error=None, retryable=False, started_at=time.time())
        future = INDEX_EXECUTOR.submit(_run_index_job, document_id, job_id)
        ACTIVE_INDEX_JOBS[document_id] = future
        future.add_done_callback(lambda completed: _forget_completed_index_job(document_id, completed))
        return get_index_status(document_id)


def start_document_import(content: bytes, filename: str) -> dict:
    """Persist an upload and schedule parsing, chunking, and indexing off-request."""
    if len(content) > MAX_FILE_SIZE:
        raise AppError('DOCUMENT_TOO_LARGE', '每份资料不能超过 20 MB', 413)
    cleaned, extension = validate_filename(filename)
    with DOCUMENT_LOCK:
        document_id = 'doc_' + uuid.uuid4().hex
        document = {'document_id': document_id, 'filename': cleaned, 'extension': extension,
                    'file_type': extension.lstrip('.'), 'mime_type': _mime_type(extension),
                    'preview_available': extension in {'.pdf', '.png', '.jpg', '.jpeg'},
                    'size_bytes': len(content), 'pages': 0,
                    'chunks': 0, 'status': 'uploaded', 'content': [], 'trace': [],
                    'index_status': {'job_id': None, 'status': 'uploaded', 'phase': 'uploaded',
                        'completed_chunks': 0, 'total_chunks': None, 'percent': None,
                        'retryable': True, 'error': None, 'updated_at': time.time()}}
        DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
        _save_document(document)
        (DOCUMENT_DIR / f'{document_id}{extension}').write_bytes(content)
    return start_index_job(document_id)


def import_document(content: bytes, filename: str) -> dict:
    with DOCUMENT_LOCK:
        document_id = 'doc_' + uuid.uuid4().hex
        prepared = _prepare_document(content, filename, document_id)
        document = {'document_id': document_id, **prepared, 'status': 'parsed',
                    'index_status': {'job_id': None, 'status': 'uploaded', 'phase': 'uploaded',
                        'completed_chunks': 0, 'total_chunks': len(prepared['content']),
                        'percent': None, 'retryable': True, 'error': None,
                        'updated_at': time.time()}}
        DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
        _save_document(document)
        (DOCUMENT_DIR / f"{document_id}{document['extension']}").write_bytes(content)
        return {k: v for k, v in document.items() if k != 'content'}


def delete_document(document_id: str) -> None:
    with INDEX_JOB_LOCK:
        active = ACTIVE_INDEX_JOBS.get(document_id)
        if active is not None and not active.done():
            raise AppError('INDEX_IN_PROGRESS', '文档索引仍在进行，请完成后再删除', 409)
        with DOCUMENT_LOCK:
            document = load_document(document_id)
            from app.services.vector_store import remove_index
            remove_index(document_id)
            document_path(document_id).unlink()
            extension = document.get('extension') or Path(document['filename']).suffix.lower()
            (DOCUMENT_DIR / f'{document_id}{extension}').unlink(missing_ok=True)


def index_document(document_id: str) -> dict:
    with INDEX_JOB_LOCK:
        active = ACTIVE_INDEX_JOBS.get(document_id)
        if active is not None and not active.done():
            raise AppError('INDEX_IN_PROGRESS', '文档索引仍在进行，请完成后再重建', 409)
        with DOCUMENT_LOCK:
            from app.services.vector_store import build_index
            document = load_document(document_id)
            started = time.perf_counter()
            if not document.get('content'):
                original, filename = original_file_path(document_id)
                document.update(_prepare_document(original.read_bytes(), filename, document_id))
            build_index(document)
            document['status'] = 'indexed'
            document['index_status'] = {'job_id': None, 'status': 'indexed', 'phase': 'indexed',
                'completed_chunks': len(document['content']), 'total_chunks': len(document['content']),
                'percent': 100, 'retryable': False, 'error': None, 'updated_at': time.time()}
            document['trace'] = [step for step in document.get('trace', []) if step['step'] != 'embedding'] + [{'step': 'embedding', 'name': 'embedding',
                'status': 'success', 'duration_ms': round((time.perf_counter()-started)*1000)}]
            _save_document(document)
            return _public_document(document)


def analyze_document(document_id: str) -> dict:
    document = load_document(document_id)
    processing = document.get('processing')
    if processing is None:
        extension = document.get('extension') or Path(document['filename']).suffix.lower()
        path, filename = original_file_path(document_id)
        if extension == '.pdf':
            result = process_document(path.read_bytes(), document_id)
            processing = {'metadata': result['metadata'], 'complexity': result['complexity'],
                          'quality': result['quality'], 'formulas': result['formulas'],
                          'tables': extract_from_pages(result['pages'], filename, document_id),
                          'tree': result['tree'].to_dict(),
                          'headings': [heading for page in result['pages'] for heading in page.headings],
                          'pages': [{'page': page.page, 'metadata': page.metadata} for page in result['pages']]}
        else:
            parsed = parse_document(path.read_bytes(), filename)
            processing = {'tables': [{**table, 'document_id': document_id, 'filename': filename}
                                     for table in parsed.tables],
                          'pages': [{'page': page['page'], 'locator': page.get('locator'),
                                     'kind': page.get('kind')} for page in parsed.pages]}
    return {'document_id': document_id, 'filename': document['filename'], **processing,
            'trace': document.get('trace', [])}

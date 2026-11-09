from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import FileResponse
from fastapi.responses import Response
from app.core.errors import AppError
from app.services.document_service import (import_document, list_documents, delete_document,
    index_document, start_index_job, start_document_import, get_index_status, original_pdf_path,
    original_file_path, render_document_page, MAX_FILE_SIZE, MAX_DOCUMENTS_PER_BATCH, MAX_TOTAL_SIZE,
    analyze_document)

router = APIRouter(prefix='/documents', tags=['documents'])


@router.post('/upload')
def upload(files: list[UploadFile] | None = File(default=None),
           file: UploadFile | None = File(default=None),
           background: bool = Query(default=False)) -> dict:
    uploads = list(files or [])
    if file is not None:
        uploads.append(file)
    try:
        if not uploads:
            raise AppError('NO_DOCUMENTS', '请至少选择一份资料', 422)
        if len(uploads) > MAX_DOCUMENTS_PER_BATCH:
            raise AppError('DOCUMENT_COUNT_LIMIT', '单次最多上传 10 份资料', 413)
        batch = [(item, item.file.read(MAX_FILE_SIZE + 1)) for item in uploads]
        if sum(len(content) for _, content in batch) > MAX_TOTAL_SIZE:
            raise AppError('TOTAL_DOCUMENT_SIZE_LIMIT', '单次上传资料总大小不能超过 100 MB', 413)
        documents, errors = [], []
        for upload_file, content in batch:
            filename = upload_file.filename or 'material'
            if len(content) > MAX_FILE_SIZE:
                errors.append({'filename': filename,
                    'error': {'code': 'DOCUMENT_TOO_LARGE', 'message': '每份资料不能超过 20 MB',
                              'status_code': 413}})
                continue
            try:
                if background:
                    imported = start_document_import(content, filename)
                else:
                    parsed = import_document(content, filename)
                    imported = index_document(parsed['document_id'])
                documents.append(imported)
            except AppError as error:
                errors.append({'filename': filename,
                    'error': {'code': error.code, 'message': error.message,
                              'status_code': error.status_code}})
        if not documents and errors:
            first_error = errors[0]['error']
            raise AppError(first_error['code'], first_error['message'], first_error['status_code'])
        response = {'success': True, 'documents': documents, 'errors': errors}
        if len(uploads) == 1 and len(documents) == 1:
            response.update(documents[0])
        return response
    finally:
        for upload_file in uploads:
            upload_file.file.close()


@router.get('')
def documents() -> dict:
    return {'success': True, 'documents': list_documents()}


@router.get('/{document_id}/file')
def original_file(document_id: str) -> FileResponse:
    path, filename = original_file_path(document_id)
    media_type = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.csv': 'text/csv', '.txt': 'text/plain', '.md': 'text/markdown',
        '.markdown': 'text/markdown', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    }.get(path.suffix.lower(), 'application/octet-stream')
    return FileResponse(path, media_type=media_type, filename=filename,
                        content_disposition_type='inline',
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/{document_id}/analysis')
def analysis(document_id: str) -> dict:
    return {'success': True, **analyze_document(document_id)}


@router.get('/{document_id}/pages/{page_number}/preview')
def preview_page(document_id: str, page_number: int) -> Response:
    image = render_document_page(document_id, page_number)
    return Response(image, media_type='image/png',
                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/{document_id}/index')
def reindex(document_id: str, background: bool = Query(default=False)) -> dict:
    indexed = start_index_job(document_id) if background else index_document(document_id)
    return {'success': True, **indexed}


@router.get('/{document_id}/index-status')
def index_status(document_id: str) -> dict:
    return {'success': True, **get_index_status(document_id)}


@router.delete('/{document_id}')
def remove(document_id: str) -> dict:
    delete_document(document_id)
    return {'success': True}

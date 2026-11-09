import pymupdf
from app.core.errors import AppError


def parse_pdf(content: bytes) -> list[dict]:
    """Extract text by page; reject image-only, encrypted, malformed PDFs."""
    if not content.startswith(b'%PDF-'):
        raise AppError('INVALID_PDF', '文件不是有效 PDF')
    try:
        with pymupdf.open(stream=content, filetype='pdf') as document:
            if document.needs_pass:
                raise AppError('ENCRYPTED_PDF', '暂不支持加密 PDF')
            if not 0 < len(document) <= 100:
                raise AppError('PDF_PAGE_LIMIT', '仅支持 1–100 页文本 PDF')
            pages = [{'page': index + 1, 'text': page.get_text('text').strip()} for index, page in enumerate(document)]
    except AppError:
        raise
    except Exception:
        raise AppError('PDF_PARSE_FAILED', 'PDF 解析失败，请使用普通文本 PDF') from None
    if not any(page['text'] for page in pages):
        raise AppError('PDF_NO_TEXT', '未提取到文本；暂不支持扫描 PDF 或 OCR')
    return pages

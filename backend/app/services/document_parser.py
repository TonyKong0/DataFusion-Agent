"""Format-aware document extraction used by the local indexing pipeline.

The parser deliberately returns page-shaped records for every supported format.
This keeps provenance stable for the vector store while allowing non-PDF sources
to expose a useful locator such as a worksheet and row range.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pymupdf

from app.core.errors import AppError

MAX_PAGES = 100
SUPPORTED_EXTENSIONS = {
    '.pdf', '.docx', '.xlsx', '.csv', '.txt', '.md', '.markdown', '.png', '.jpg', '.jpeg',
}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}


@dataclass(frozen=True)
class ParsedDocument:
    """Extracted pages plus the normalized format metadata."""

    filename: str
    extension: str
    mime_type: str
    pages: list[dict]
    preview_available: bool = False
    tables: list[dict] = field(default_factory=list)


def safe_filename(filename: str | None) -> str:
    """Return a short basename without allowing path traversal."""
    value = (filename or 'document').replace('\\', '/').split('/')[-1].strip()
    value = re.sub(r'[\x00-\x1f\x7f]', '_', value)[:200]
    return value or 'document'


def file_extension(filename: str) -> str:
    return Path(safe_filename(filename)).suffix.lower()


def validate_filename(filename: str | None) -> tuple[str, str]:
    cleaned = safe_filename(filename)
    extension = file_extension(cleaned)
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError('UNSUPPORTED_DOCUMENT_TYPE', '支持 PDF、DOCX、XLSX、CSV、TXT、Markdown、PNG、JPG 文件')
    return cleaned, extension


def _page(page: int, text: str, **locator: object) -> dict:
    item = {'page': page, 'text': text.strip()}
    if locator:
        item['locator'] = locator
    return item


def _ensure_page_limit(pages: list[dict]) -> list[dict]:
    if not 0 < len(pages) <= MAX_PAGES:
        raise AppError('DOCUMENT_PAGE_LIMIT', '单个文件最多支持 100 页或等价的来源分段')
    if not any(page.get('text', '').strip() for page in pages):
        raise AppError('DOCUMENT_NO_TEXT', '未提取到可检索文本')
    return pages


def _decode_text(content: bytes) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030', 'big5'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AppError('DOCUMENT_DECODE_FAILED', '文本文件编码无法识别')


_OCR_ENGINE = None


def _ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
        except Exception:
            raise AppError('OCR_UNAVAILABLE', 'RapidOCR/ONNX Runtime 不可用，请检查安装环境', 503) from None
    return _OCR_ENGINE


def ocr_image(image: np.ndarray) -> str:
    """Run RapidOCR and return only recognized text.

    RapidOCR has returned both ``(result, elapsed)`` and a bare result across
    releases, so the small compatibility branch is intentionally kept here.
    """
    engine = _ocr_engine()
    try:
        output = engine(image)
        result = output[0] if isinstance(output, tuple) else output
        texts = []
        for item in result or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                value = item[1]
                if isinstance(value, (list, tuple)):
                    value = value[0] if value else ''
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
        return '\n'.join(texts)
    except AppError:
        raise
    except Exception:
        raise AppError('OCR_FAILED', '图片文字识别失败', 422) from None


def _pixmap_array(pixmap: pymupdf.Pixmap) -> np.ndarray:
    channels = pixmap.n
    data = np.frombuffer(pixmap.samples, dtype=np.uint8)
    return data.reshape(pixmap.height, pixmap.width, channels)


def _parse_pdf(content: bytes) -> tuple[list[dict], bool]:
    if not content.startswith(b'%PDF-'):
        raise AppError('INVALID_PDF', '文件不是有效 PDF')
    try:
        with pymupdf.open(stream=content, filetype='pdf') as document:
            if document.needs_pass:
                raise AppError('ENCRYPTED_PDF', '暂不支持加密 PDF')
            if not 0 < len(document) <= MAX_PAGES:
                raise AppError('PDF_PAGE_LIMIT', '仅支持 1–100 页 PDF')
            pages = []
            for index, page in enumerate(document):
                text = page.get_text('text').strip()
                images = page.get_images(full=True)
                if not text and images:
                    # Render at a readable scale before OCR.  The original PDF
                    # is kept separately, so this does not alter citations.
                    scale = min(2.0, 1800 / max(page.rect.width, page.rect.height))
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    text = ocr_image(_pixmap_array(pixmap))
                pages.append(_page(index + 1, text, kind='pdf'))
    except AppError:
        raise
    except Exception:
        raise AppError('PDF_PARSE_FAILED', 'PDF 解析失败，请检查文件内容') from None
    # An empty text-only PDF is still a malformed input for retrieval.  A scan
    # with images gets a useful OCR-specific error if recognition found nothing.
    if not any(item['text'] for item in pages):
        raise AppError('PDF_NO_TEXT', '未提取到文本，扫描页面请确保图片清晰')
    return _ensure_page_limit(pages), True


def _parse_image(content: bytes, extension: str) -> tuple[list[dict], bool]:
    try:
        with pymupdf.open(stream=content, filetype=extension.lstrip('.')) as image:
            page = image[0]
            text = ocr_image(_pixmap_array(page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)))
    except AppError:
        raise
    except Exception:
        raise AppError('IMAGE_PARSE_FAILED', '图片文件解析失败') from None
    return _ensure_page_limit([_page(1, text, kind='image')]), True


def _table_asset(rows: list[list[str]], index: int, *, page: int = 1,
                 title: str | None = None, sheet: str | None = None) -> dict | None:
    rows = [[re.sub(r'\s+', ' ', value).strip() for value in row] for row in rows]
    rows = [row for row in rows if any(row)]
    width = max((len(row) for row in rows), default=0)
    if len(rows) < 2 or width < 2:
        return None
    padded = [(row + [''] * width)[:width] for row in rows]
    return {'page': page, 'table_index': index, 'title': title or f'表格 {index}',
            'sheet': sheet, 'headers': padded[0], 'rows': padded[1:],
            'source': 'spreadsheet' if sheet else 'document_table'}


def _parse_docx(content: bytes) -> tuple[list[dict], bool, list[dict]]:
    try:
        from docx import Document
        document = Document(io.BytesIO(content))
        parts = []
        for paragraph in document.paragraphs:
            value = paragraph.text.strip()
            if value:
                parts.append(value)
        tables = []
        for table_index, table in enumerate(document.tables, start=1):
            cells = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            rows = [' | '.join(row) for row in cells]
            value = '\n'.join(item for item in rows if item.strip())
            if value:
                parts.append(f'[表格 {table_index}]\n{value}')
            asset = _table_asset(cells, table_index, title=f'DOCX 表格 {table_index}')
            if asset:
                tables.append(asset)
    except ImportError:
        raise AppError('DOCX_PARSER_UNAVAILABLE', 'DOCX 解析依赖未安装', 503) from None
    except Exception:
        raise AppError('DOCX_PARSE_FAILED', 'DOCX 文件解析失败') from None
    return _ensure_page_limit([_page(1, '\n'.join(parts), kind='docx', section='document')]), False, tables


def _parse_xlsx(content: bytes) -> tuple[list[dict], bool, list[dict]]:
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        pages = []
        tables = []
        for sheet_index, sheet in enumerate(workbook.worksheets, start=1):
            rows = []
            structured_rows = []
            first_row = None
            last_row = None
            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = [str(value) if value is not None else '' for value in row]
                line = ' | '.join(values).strip()
                if line:
                    first_row = row_index if first_row is None else first_row
                    last_row = row_index
                    rows.append(line)
                    structured_rows.append(values)
            if rows:
                pages.append(_page(sheet_index, '\n'.join(rows), kind='xlsx', sheet=sheet.title,
                                   row_start=first_row, row_end=last_row))
                asset = _table_asset(structured_rows, len(tables) + 1, page=sheet_index,
                                     title=sheet.title, sheet=sheet.title)
                if asset:
                    tables.append(asset)
        workbook.close()
    except ImportError:
        raise AppError('XLSX_PARSER_UNAVAILABLE', 'XLSX 解析依赖未安装', 503) from None
    except Exception:
        raise AppError('XLSX_PARSE_FAILED', 'XLSX 文件解析失败') from None
    return _ensure_page_limit(pages), False, tables


def _parse_csv(content: bytes) -> tuple[list[dict], bool, list[dict]]:
    text = _decode_text(content)
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    rows = []
    structured_rows = []
    for row in csv.reader(io.StringIO(text), dialect):
        values = [str(value).strip() for value in row]
        if any(values):
            structured_rows.append(values)
            rows.append(' | '.join(values))
    value = '\n'.join(rows)
    table = _table_asset(structured_rows, 1, title='CSV 数据')
    if table:
        table['source'] = 'spreadsheet'
    return (_ensure_page_limit([_page(1, value, kind='csv', row_start=1, row_end=len(rows))]),
            False, [table] if table else [])


def _parse_text(content: bytes, extension: str) -> tuple[list[dict], bool]:
    text = _decode_text(content)
    return _ensure_page_limit([_page(1, text, kind='markdown' if extension in {'.md', '.markdown'} else 'text')]), False


def parse_document(content: bytes, filename: str | None) -> ParsedDocument:
    """Parse one supported upload into source pages.

    File size and batch quotas are enforced by the API/service layer because
    this function is also useful for direct unit tests and background retries.
    """
    cleaned, extension = validate_filename(filename)
    tables = []
    if extension == '.pdf':
        pages, preview = _parse_pdf(content)
        mime = 'application/pdf'
    elif extension in IMAGE_EXTENSIONS:
        pages, preview = _parse_image(content, extension)
        mime = 'image/jpeg' if extension in {'.jpg', '.jpeg'} else 'image/png'
    elif extension == '.docx':
        pages, preview, tables = _parse_docx(content)
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif extension == '.xlsx':
        pages, preview, tables = _parse_xlsx(content)
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif extension == '.csv':
        pages, preview, tables = _parse_csv(content)
        mime = 'text/csv'
    else:
        pages, preview = _parse_text(content, extension)
        mime = 'text/markdown' if extension in {'.md', '.markdown'} else 'text/plain'
    return ParsedDocument(cleaned, extension, mime, pages, preview, tables)


def parse_pdf(content: bytes) -> list[dict]:
    """Backward-compatible text/OCR PDF parser used by existing callers."""
    return parse_document(content, 'document.pdf').pages

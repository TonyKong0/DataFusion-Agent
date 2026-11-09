import re
import pymupdf


def normalize_table(raw: dict, page: int, index: int, filename: str, document_id: str) -> dict | None:
    rows = [[re.sub(r'\s+', ' ', str(cell or '')).strip() for cell in row]
            for row in raw.get('rows', []) if row]
    rows = [row for row in rows if any(row)]
    if len(rows) < 2 or len(rows[0]) < 2:
        return None
    width = len(rows[0])
    body = [(row + [''] * width)[:width] for row in rows[1:]]
    return {'document_id': document_id, 'filename': filename, 'page': page,
            'table_index': index, 'title': raw.get('title') or f'第 {page} 页表格 {index}',
            'headers': rows[0], 'rows': body, 'bbox': raw.get('bbox'),
            'source': raw.get('source', 'pdf_table')}


def extract_tables(document_id: str) -> list[dict]:
    from app.services.document_service import load_document, original_pdf_path
    document = load_document(document_id)
    filename = document['filename']
    extension = document.get('extension') or filename.rsplit('.', 1)[-1].lower()
    saved = document.get('processing', {}).get('tables')
    if isinstance(saved, list):
        return [{**table, 'extension': extension,
                 'preview_available': bool(document.get('preview_available'))}
                for table in saved]
    path, _ = original_pdf_path(document_id)
    tables = []
    with pymupdf.open(path) as pdf:
        for page_number, page in enumerate(pdf, 1):
            try:
                found = page.find_tables().tables
            except Exception:
                found = []
            for index, item in enumerate(found, 1):
                normalized = normalize_table({'rows': item.extract(), 'bbox': list(item.bbox)},
                                             page_number, index, filename, document_id)
                if normalized:
                    tables.append(normalized)
    return [{**table, 'extension': extension, 'preview_available': extension == '.pdf'}
            for table in tables]


def extract_from_pages(pages: list, filename: str, document_id: str) -> list[dict]:
    tables = []
    for page in pages:
        native = list(page.tables)
        if not native and page.metadata.get('ocr_used'):
            lines = [line.strip() for line in page.text.splitlines() if '|' in line]
            rows = [[cell.strip() for cell in line.strip('|').split('|')] for line in lines]
            if len(rows) >= 2 and len({len(row) for row in rows}) == 1:
                native = [{'rows': rows, 'source': 'ocr_delimited'}]
        for index, raw in enumerate(native, 1):
            table = normalize_table(raw, page.page, index, filename, document_id)
            if table:
                tables.append(table)
    return tables

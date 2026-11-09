import pymupdf
from app.document.models import DocumentPage


def parse_native(content: bytes, document_id: str) -> list[DocumentPage]:
    pages = []
    with pymupdf.open(stream=content, filetype='pdf') as pdf:
        for number, page in enumerate(pdf, 1):
            blocks = []
            for block in page.get_text('dict').get('blocks', []):
                if block.get('type') != 0:
                    continue
                lines = []
                sizes = []
                bold = False
                for line in block.get('lines', []):
                    for span in line.get('spans', []):
                        lines.append(span.get('text', ''))
                        sizes.append(span.get('size', 0))
                        bold |= 'bold' in span.get('font', '').lower()
                text = ''.join(lines).strip()
                if text:
                    blocks.append({'text': text, 'bbox': list(block['bbox']),
                                   'font_size': max(sizes, default=0), 'bold': bold})
            try:
                tables = [{'bbox': list(table.bbox), 'rows': table.extract()}
                          for table in page.find_tables().tables]
            except Exception:
                tables = []
            pages.append(DocumentPage(document_id, number, page.get_text('text').strip(),
                blocks=blocks, tables=tables,
                metadata={'rotation': page.rotation, 'parser': 'native', 'ocr_used': False}))
    return pages

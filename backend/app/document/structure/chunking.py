from app.services.text_splitter import split_pages
from app.document.structure.heading_detector import detect_headings
from app.document.structure.models import Heading


def split_hierarchical(pages: list, document_id: str, filename: str,
                       chunk_size: int = 800) -> list[dict]:
    headings = ([Heading(**item) for page in pages for item in page.headings]
                if any(page.headings for page in pages) else detect_headings(pages))
    if not headings:
        return split_pages([{'page': page.page, 'text': page.text} for page in pages], document_id, filename)
    by_page = {}
    for heading in headings:
        by_page.setdefault(heading.page, {})[heading.title] = heading
    chunks = []
    path = []
    for page in pages:
        sections = []
        current = []
        current_path = path[:]
        for line in page.text.splitlines():
            heading = by_page.get(page.page, {}).get(line.strip())
            if heading:
                if current:
                    sections.append((current_path, '\n'.join(current)))
                path = path[:heading.level - 1] + [heading.title]
                current_path = path[:]
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append((current_path, '\n'.join(current)))
        for heading_path, text in sections:
            if not text.strip():
                continue
            lines = text.splitlines()
            group = []
            for line in lines:
                if group and len('\n'.join(group)) + len(line) + 1 > chunk_size:
                    _append(chunks, document_id, filename, page.page, heading_path, '\n'.join(group))
                    group = []
                if len(line) > chunk_size:
                    if group:
                        _append(chunks, document_id, filename, page.page, heading_path, '\n'.join(group))
                        group = []
                    for start in range(0, len(line), chunk_size):
                        _append(chunks, document_id, filename, page.page, heading_path,
                                line[start:start + chunk_size])
                else:
                    group.append(line)
            if group:
                _append(chunks, document_id, filename, page.page, heading_path, '\n'.join(group))
    return chunks


def _append(chunks, document_id, filename, page, heading_path, text):
    if text.strip():
        chunks.append({'chunk_id': f'{document_id}_chunk_{len(chunks)+1:04}',
                       'document_id': document_id, 'filename': filename, 'page': page,
                       'chapter': heading_path[0] if heading_path else None,
                       'section': heading_path[-1] if heading_path else None,
                       'heading_path': heading_path[:], 'text': text})

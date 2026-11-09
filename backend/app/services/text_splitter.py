def split_pages(pages: list[dict], document_id: str, filename: str,
                chunk_size: int = 800, overlap: int = 120) -> list[dict]:
    """Keep page provenance and overlapping character windows."""
    if chunk_size <= overlap or overlap < 0:
        raise ValueError('invalid chunk parameters')
    chunks = []
    for page in pages:
        text = page['text']
        start = 0
        while start < len(text):
            fragment = text[start:start+chunk_size]
            if fragment.strip():
                chunk = {'chunk_id': f'{document_id}_chunk_{len(chunks)+1:04}',
                    'document_id': document_id, 'filename': filename, 'page': page['page'], 'text': fragment}
                if page.get('locator'):
                    chunk['locator'] = page['locator']
                if page.get('kind'):
                    chunk['kind'] = page['kind']
                chunks.append(chunk)
            if start + chunk_size >= len(text):
                break
            start += chunk_size - overlap
    return chunks

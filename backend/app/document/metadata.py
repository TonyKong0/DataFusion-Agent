def summarize_pages(pages: list) -> dict:
    return {'pages': len(pages), 'native_pages': sum(p.metadata.get('parser') == 'native' for p in pages),
            'ocr_pages': sum(bool(p.metadata.get('ocr_used')) for p in pages)}

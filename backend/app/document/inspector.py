"""Read PDF page metadata without changing the original RAG parser."""
import pymupdf
from app.core.errors import AppError


def inspect_pdf(content: bytes) -> list[dict]:
    if not content.startswith(b'%PDF-'):
        raise AppError('INVALID_PDF', '文件不是有效 PDF')
    try:
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            if pdf.needs_pass:
                raise AppError('ENCRYPTED_PDF', '暂不支持加密 PDF')
            if not 0 < len(pdf) <= 100:
                raise AppError('PDF_PAGE_LIMIT', '仅支持 1–100 页 PDF')
            pages = []
            for i, page in enumerate(pdf):
                blocks = page.get_text('dict').get('blocks', [])
                text_blocks = [block for block in blocks if block.get('type') == 0]
                image_blocks = [block for block in blocks if block.get('type') == 1]
                area = max(page.rect.width * page.rect.height, 1)
                image_area = sum(max(0, b['bbox'][2]-b['bbox'][0]) * max(0, b['bbox'][3]-b['bbox'][1]) for b in image_blocks)
                pages.append({'page': i + 1, 'text': page.get_text('text').strip(),
                              'text_blocks': len(text_blocks), 'image_count': len(image_blocks),
                              'image_ratio': min(1.0, image_area / area), 'rotation': page.rotation})
            return pages
    except AppError:
        raise
    except Exception:
        raise AppError('PDF_PARSE_FAILED', 'PDF 解析失败') from None

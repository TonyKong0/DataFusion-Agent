from functools import lru_cache
import numpy as np
import pymupdf
from app.core.errors import AppError
from app.document.models import DocumentPage


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception:
        raise AppError('OCR_UNAVAILABLE', 'OCR 引擎不可用，请安装后端 OCR 依赖', 503) from None


def _rotate(image: np.ndarray, angle: int) -> np.ndarray:
    if angle == 90:
        return np.rot90(image, 1).copy()
    if angle == 180:
        return np.rot90(image, 2).copy()
    if angle == 270:
        return np.rot90(image, 3).copy()
    return image


def parse_ocr_page(content: bytes, document_id: str, page_number: int, rotation: int = 0) -> DocumentPage:
    try:
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            page = pdf[page_number - 1]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
        engine = _engine()
        best = ([], 0.0, 0)
        for angle in (0, 90, 180, 270):
            result, _ = engine(_rotate(image, angle))
            lines = result or []
            score = sum(len(item[1]) * float(item[2]) for item in lines)
            if score > best[1]:
                best = (lines, score, angle)
            if score >= 40 and lines and sum(float(item[2]) for item in lines) / len(lines) >= .8:
                break
        lines, _, angle = best
        text = '\n'.join(item[1] for item in lines).strip()
        if not text:
            raise AppError('OCR_NO_TEXT', f'第 {page_number} 页 OCR 未识别到文字', 422)
        return DocumentPage(document_id, page_number, text,
            blocks=[{'text': item[1], 'bbox': item[0], 'ocr_confidence': round(float(item[2]), 3)} for item in lines],
            metadata={'rotation': rotation, 'ocr_rotation': angle, 'parser': 'ocr', 'ocr_used': True,
                      'ocr_confidence': round(sum(float(item[2]) for item in lines) / len(lines), 3)})
    except AppError:
        raise
    except Exception:
        raise AppError('OCR_FAILED', f'第 {page_number} 页 OCR 失败，请检查扫描件质量', 422) from None

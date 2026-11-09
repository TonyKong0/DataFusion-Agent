from app.document.quality.models import QualityIssue


def detect_rotation(page) -> list[QualityIssue]:
    degree = page.metadata.get('rotation', 0)
    ocr_degree = page.metadata.get('ocr_rotation', 0)
    if degree in (90, 180, 270) or ocr_degree in (90, 180, 270):
        return [QualityIssue(page.page, 'rotation', 'medium',
            f'页面旋转 {degree or ocr_degree}°，预览保留原始页',
            {'pdf_rotation': degree, 'ocr_correction': ocr_degree})]
    return []

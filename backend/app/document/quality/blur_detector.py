import cv2
import numpy as np
import pymupdf
from app.document.quality.models import QualityIssue


def detect_blur(content: bytes, page_number: int, threshold: float = 75) -> list[QualityIssue]:
    with pymupdf.open(stream=content, filetype='pdf') as pdf:
        pix = pdf[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if variance < threshold:
        return [QualityIssue(page_number, 'blur', 'medium', '扫描图像清晰度较低',
                             {'laplacian_variance': round(variance, 2), 'threshold': threshold})]
    return []

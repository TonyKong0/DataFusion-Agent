from app.document.models import DocumentPage
from app.document.quality.rotation_detector import detect_rotation
from app.document.quality.text_quality import detect_text_issues
from app.document.quality.blur_detector import detect_blur
import pymupdf


def test_rotation_and_low_ocr_have_page_evidence():
    page = DocumentPage('d', 3, '文档识别结果', metadata={'rotation': 90, 'ocr_used': True, 'ocr_confidence': .42})
    assert detect_rotation(page)[0].page == 3
    issues = detect_text_issues(page)
    assert any(item.type == 'low_ocr_confidence' and item.evidence['confidence'] == .42 for item in issues)


def test_blank_and_corrupt_text():
    blank = DocumentPage('d', 4, '')
    corrupt = DocumentPage('d', 5, '正常文字\ufffd\ufffd')
    assert detect_text_issues(blank)[0].type == 'blank_page'
    assert any(item.type == 'anomalous_characters' for item in detect_text_issues(corrupt))


def test_blur_detector_records_page_and_measurement():
    with pymupdf.open() as pdf:
        pdf.new_page()
        issues = detect_blur(pdf.tobytes(), 1)
    assert issues[0].type == 'blur' and issues[0].page == 1
    assert 'laplacian_variance' in issues[0].evidence

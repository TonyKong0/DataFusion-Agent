import pymupdf
from app.document.ocr.detector import detect_scan
from app.document.parser_router import select_parser
from app.document.pipeline import process_document


def test_scan_routing_does_not_ocr_normal_or_blank_page():
    assert select_parser({'text': 'normal text '*20, 'text_blocks': 1, 'image_count': 0, 'image_ratio': 0}) == 'native'
    assert select_parser({'text': '', 'text_blocks': 0, 'image_count': 1, 'image_ratio': .9}) == 'ocr'
    assert not detect_scan({'text': '', 'image_count': 0, 'image_ratio': 0})['is_scanned']


def test_native_pdf_still_skips_ocr():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Ordinary text PDF remains native')
        result = process_document(pdf.tobytes(), 'doc_test')
    assert result['pages'][0].metadata['ocr_used'] is False

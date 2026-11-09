from app.document.native_pdf_parser import parse_native
from app.document.ocr.detector import detect_scan
from app.document.ocr.ocr_service import parse_ocr_page


def select_parser(page_inspection: dict) -> str:
    return 'ocr' if detect_scan(page_inspection)['is_scanned'] else 'native'


def parse(content: bytes, document_id: str, inspections: list[dict]):
    pages = parse_native(content, document_id)
    for index, inspection in enumerate(inspections):
        detection = detect_scan(inspection)
        pages[index].metadata['scan_detection'] = detection
        if select_parser(inspection) == 'ocr':
            pages[index] = parse_ocr_page(content, document_id, inspection['page'], inspection['rotation'])
            pages[index].metadata['scan_detection'] = detection
    return pages

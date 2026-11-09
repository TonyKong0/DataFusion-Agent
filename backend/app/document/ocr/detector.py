from app.document.ocr.models import ScanDetection


def detect_scan(page: dict) -> dict:
    text_len = len(page.get('text', '').strip())
    image_ratio = float(page.get('image_ratio', 0))
    image_count = int(page.get('image_count', 0))
    blocks = int(page.get('text_blocks', 0))
    reasons = []
    if text_len < 40:
        reasons.append('extractable_text_too_low')
    if blocks <= 1:
        reasons.append('text_blocks_low')
    if image_ratio >= .45:
        reasons.append('page_image_ratio_high')
    scanned = text_len < 40 and image_count > 0 and image_ratio >= .35
    confidence = min(.99, .55 + image_ratio * .4) if scanned else min(.99, .65 + min(text_len, 200) / 600)
    return ScanDetection(scanned, round(confidence, 3), reasons).to_dict()

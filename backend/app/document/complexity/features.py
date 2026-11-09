import re
from app.document.ocr.detector import detect_scan


def extract_features(inspections: list[dict]) -> dict:
    count = max(len(inspections), 1)
    texts = [item.get('text', '') for item in inspections]
    headings = sum(bool(re.match(r'^\s*(?:第[一二三四五六七八九十\d]+章|\d+(?:\.\d+)+|[一二三四五六七八九十]+、)', line))
                   for text in texts for line in text.splitlines())
    formulas = sum(bool(re.search(r'[=＝].*[+\-×*/÷]', line))
                   for text in texts for line in text.splitlines())
    blocks = [item.get('text_blocks', 0) for item in inspections]
    return {'pages': len(inspections),
            'scan_ratio': sum(item.get('was_scanned', detect_scan(item)['is_scanned']) for item in inspections) / count,
            'image_count': sum(item.get('image_count', 0) for item in inspections),
            'formula_count': formulas, 'heading_count': headings,
            'heading_depth_estimate': min(3, max((line.count('.') + 1 for text in texts for line in text.splitlines()
                if re.match(r'^\d+(?:\.\d+)+', line)), default=0)),
            'avg_text_blocks': sum(blocks) / count,
            'layout_variation': (max(blocks) - min(blocks)) / max(max(blocks), 1) if blocks else 0}

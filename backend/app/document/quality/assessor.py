from app.document.quality.rotation_detector import detect_rotation
from app.document.quality.blur_detector import detect_blur
from app.document.quality.text_quality import detect_text_issues
from app.document.quality.models import QualityIssue
from pathlib import Path
import yaml

RULES = yaml.safe_load((Path(__file__).with_name('rules.yaml')).read_text(encoding='utf-8'))


def assess_quality(content: bytes, pages: list) -> dict:
    issues = []
    for page in pages:
        issues.extend(detect_rotation(page))
        issues.extend(detect_text_issues(page, RULES['anomalous_character_ratio'],
                                         RULES['low_ocr_confidence']))
        if page.metadata.get('ocr_used'):
            issues.append(QualityIssue(page.page, 'scanned_page', 'low',
                '扫描页已使用 OCR 解析', {'ocr_confidence': page.metadata.get('ocr_confidence')}))
            issues.extend(detect_blur(content, page.page, RULES['blur_laplacian_threshold']))
    penalty = sum({'high': 18, 'medium': 10, 'low': 4}[item.severity] for item in issues)
    score = max(0, 100 - penalty)
    level = 'High' if score >= 80 else 'Medium' if score >= 50 else 'Low'
    return {'quality_score': score, 'level': level,
            'issues': [item.to_dict() for item in issues]}

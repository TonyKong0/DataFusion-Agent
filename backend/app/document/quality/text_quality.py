from app.document.quality.models import QualityIssue

TRADITIONAL = set('體學國書會發個門東車馬醫術網頁產業時後對應為與萬億點選錄檔')


def detect_text_issues(page, anomalous_ratio: float = .02,
                       low_ocr_confidence: float = .65) -> list[QualityIssue]:
    text = page.text.strip()
    issues = []
    if not text:
        issues.append(QualityIssue(page.page, 'blank_page', 'medium', '页面没有可提取文字', {'text_length': 0}))
        return issues
    if len(text) < 15 and not page.metadata.get('ocr_used'):
        issues.append(QualityIssue(page.page, 'low_text', 'low', '可提取文本较少', {'text_length': len(text)}))
    bad = sum(ch in '\ufffd\u25a1' or (ord(ch) < 32 and ch not in '\n\t\r') for ch in text)
    if bad / len(text) >= anomalous_ratio:
        issues.append(QualityIssue(page.page, 'anomalous_characters', 'medium',
                     '存在异常字符，可能影响检索', {'count': bad, 'ratio': round(bad / len(text), 3)}))
        issues.append(QualityIssue(page.page, 'suspected_typo', 'low',
                     '异常字符附近可能存在识别错字', {'marker_count': bad}))
    han = [ch for ch in text if '\u4e00' <= ch <= '\u9fff']
    if len(han) >= 20:
        ratio = sum(ch in TRADITIONAL for ch in han) / len(han)
        if ratio >= .15:
            issues.append(QualityIssue(page.page, 'traditional_chinese', 'low',
                         '繁体字比例较高', {'ratio': round(ratio, 3)}))
    confidence = page.metadata.get('ocr_confidence')
    if confidence is not None and confidence < low_ocr_confidence:
        issues.append(QualityIssue(page.page, 'low_ocr_confidence', 'high',
                     'OCR 识别置信度较低', {'confidence': confidence}))
    return issues

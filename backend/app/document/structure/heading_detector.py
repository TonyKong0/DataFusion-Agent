import re
from app.document.structure.models import Heading

PATTERNS = [
    (re.compile(r'^(?:Chapter|CHAPTER)\s+\d+\b\s*\S'), 1, .94),
    (re.compile(r'^(?:Part|PART)\s+[IVX]+\b\s*\S'), 1, .91),
    (re.compile(r'^(?:Section|SECTION)\s+\d+\b\s*\S'), 1, .92),
    (re.compile(r'^[IVX]+\.\s+\S'), 1, .83),
    (re.compile(r'^[A-Z]\.\s+\S'), 1, .80),
    (re.compile(r'^\d+[)]\s+\S'), 1, .84),
    (re.compile(r'^\d+\s+-\s+\S'), 1, .82),
    (re.compile(r'^\d+\s+[A-Z][A-Za-z]+'), 1, .75),
    (re.compile(r'^第[一二三四五六七八九十百\d]+[章节篇]\s*\S'), 1, .97),
    (re.compile(r'^\d+[.．]\d+[.．]\d+\s*\S'), 3, .96),
    (re.compile(r'^\d+[.．]\d+\s*\S'), 2, .96),
    (re.compile(r'^\d+[.．、]\s*\S'), 1, .92),
    (re.compile(r'^[一二三四五六七八九十]+[、.．]\s*\S'), 1, .92),
    (re.compile(r'^[（(][一二三四五六七八九十]+[）)]\s*\S'), 2, .90),
    (re.compile(r'^\d+[）)]\s*\S'), 3, .85),
]


def detect_headings(pages: list) -> list[Heading]:
    headings = []
    for page in pages:
        font_sizes = [b.get('font_size', 0) for b in page.blocks if b.get('font_size')]
        body_size = sorted(font_sizes)[len(font_sizes)//2] if font_sizes else 0
        block_by_text = {b.get('text', '').strip(): b for b in page.blocks}
        for line in page.text.splitlines():
            title = line.strip()
            if not 2 <= len(title) <= 65 or title.endswith(('。', '；', ';', '，', ',')):
                continue
            matched = next(((level, score) for pattern, level, score in PATTERNS if pattern.match(title)), None)
            block = block_by_text.get(title, {})
            large = bool(body_size and block.get('font_size', 0) >= body_size * 1.25)
            bold = bool(block.get('bold'))
            if matched:
                level, confidence = matched
                if large or bold:
                    confidence = min(.99, confidence + .02)
            elif (large or bold) and len(title) <= 35 and not re.search(r'[.!?。！？]$', title):
                level, confidence = (1 if large else 2), (.8 if large else .7)
            else:
                continue
            headings.append(Heading(title, level, page.page, None, confidence))
    return headings

"""Restore table structure from OCR boxes on scanned pages.

Native PDF tables come from pymupdf's table finder. Scanned pages have no text
layer, so the only signal is OCR boxes: this module clusters boxes into rows by
vertical centre and into columns by horizontal gaps, then renders a Markdown
table. Merged cells are not reconstructed; a spanning header keeps its text in
the first overlapped column, and the first row is assumed to be the header.

Short 1-2 character numbers are frequently missed by whole-page text detection.
Empty cells are therefore re-checked from a structure-derived crop of the page
image, using recognition without detection. Recovered cells keep their low
confidence so downstream answers can warn about them.
"""

import unicodedata

import cv2
import pymupdf
import numpy as np

from app.document.ocr.ocr_service import _engine

MIN_BOX_CONFIDENCE = 0.45
CELL_CONFIDENCE_WARNING = 0.6
MAX_PAGES = 5
SCANNED_TEXT_LIMIT = 40
MAX_RECOVERY_CELLS = 12
MIN_RECOVERY_CONFIDENCE = 0.2
RECOVERY_PADDING_X = 14
RECOVERY_PADDING_Y = 8


def _bounds(box) -> tuple[float, float, float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return min(xs), min(ys), max(xs), max(ys)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def labels_from_boxes(raw_lines) -> list[dict]:
    labels = []
    for item in raw_lines or []:
        text = str(item[1]).strip()
        confidence = float(item[2])
        if not text or confidence < MIN_BOX_CONFIDENCE:
            continue
        labels.append({'text': text, 'confidence': round(confidence, 3), 'bbox': item[0]})
    return labels


def cluster_rows(labels: list[dict]) -> list[list[dict]]:
    """Group boxes whose vertical centres fall within roughly half a line height."""
    if not labels:
        return []
    centres = {id(item): (_bounds(item['bbox'])[1] + _bounds(item['bbox'])[3]) / 2
               for item in labels}
    ordered = sorted(labels, key=lambda item: centres[id(item)])
    tolerance = max(4.0, _median([_bounds(item['bbox'])[3] - _bounds(item['bbox'])[1]
                                  for item in ordered]) * 0.6)
    rows, current = [], [ordered[0]]
    for item in ordered[1:]:
        row_centre = sum(centres[id(entry)] for entry in current) / len(current)
        if centres[id(item)] - row_centre > tolerance:
            rows.append(current)
            current = [item]
        else:
            current.append(item)
    rows.append(current)
    for row in rows:
        row.sort(key=lambda item: _bounds(item['bbox'])[0])
    return rows


def column_regions(labels: list[dict]) -> list[tuple[float, float]]:
    """Merge horizontal spans that are closer than one line height; gaps become columns."""
    spans = sorted((_bounds(item['bbox'])[0], _bounds(item['bbox'])[2]) for item in labels)
    gap = max(6.0, _median([_bounds(item['bbox'])[3] - _bounds(item['bbox'])[1]
                            for item in labels]) * 0.8)
    regions: list[tuple[float, float]] = []
    for start, end in spans:
        if regions and start - regions[-1][1] <= gap:
            regions[-1] = (regions[-1][0], max(regions[-1][1], end))
        else:
            regions.append((start, end))
    return regions


def build_grid(labels: list[dict]) -> tuple[list[list[str]], int, list[list[float]]]:
    """Return cell text, column count and the weakest box confidence per cell."""
    rows = cluster_rows(labels)
    regions = column_regions(labels)
    if len(rows) < 2 or len(regions) < 2:
        return [], 0, []
    grid, confidences = [], []
    for row in rows:
        cells = [''] * len(regions)
        cell_confidence = [1.0] * len(regions)
        for item in row:
            x0, _, x1, _ = _bounds(item['bbox'])
            best_index, best_overlap = 0, float('-inf')
            for index, (start, end) in enumerate(regions):
                overlap = min(x1, end) - max(x0, start)
                if overlap > best_overlap:
                    best_index, best_overlap = index, overlap
            cells[best_index] = f"{cells[best_index]} {item['text']}".strip()
            cell_confidence[best_index] = min(cell_confidence[best_index], item['confidence'])
        grid.append(cells)
        confidences.append(cell_confidence)
    return grid, len(regions), confidences


def normalize_cell_text(text: object) -> str:
    """Fold full-width digits and drop whitespace so OCR output is comparable."""
    folded = unicodedata.normalize('NFKC', str(text)).strip()
    return folded.replace(' ', '')


def _recognize_cell(crop: np.ndarray, engine) -> tuple[str, float, str]:
    """Recognize one cell crop without text detection.

    Whole-page detection misses isolated short numbers entirely, so there is no
    box to re-score. Two recognition-only views are used; the second only raises
    confidence when it agrees, it can never overrule the primary view.
    """
    try:
        primary, _ = engine.text_recognizer([crop])
    except Exception:  # noqa: BLE001 - a failed crop is simply left empty
        return '', 0.0, ''
    if not primary:
        return '', 0.0, ''
    text = normalize_cell_text(primary[0][0])
    confidence = float(primary[0][1])
    method = 'rec_only'
    try:
        padded = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT,
                                    value=(255, 255, 255))
        secondary, _ = engine.text_recognizer([padded])
        if secondary and normalize_cell_text(secondary[0][0]) == text:
            confidence = max(confidence, float(secondary[0][1]))
            method = 'agreed'
    except Exception:  # noqa: BLE001 - the primary result remains usable
        pass
    return text, confidence, method


def _valid_recovery(text: str, confidence: float) -> bool:
    return (bool(text) and len(text) <= 32 and confidence >= MIN_RECOVERY_CONFIDENCE
            and any(character.isalnum() for character in text))


def recover_empty_cells(image: np.ndarray, labels: list[dict], grid: list[list[str]],
                        confidences: list[list[float]], *, engine=None) -> list[dict]:
    """Fill empty grid cells from structure-derived crops, in place.

    Rows and column regions come from the boxes that *were* detected, so a fully
    blank row cannot be invented. The cap bounds OCR cost on large tables.
    """
    rows = cluster_rows(labels)
    regions = column_regions(labels)
    if len(rows) != len(grid) or len(regions) < 2:
        return []
    engine = engine or _engine()
    recovered: list[dict] = []
    for row_index, row in enumerate(grid):
        if len(recovered) >= MAX_RECOVERY_CELLS:
            break
        for column_index, value in enumerate(row):
            if value.strip() or len(recovered) >= MAX_RECOVERY_CELLS:
                continue
            if column_index >= len(regions):
                continue
            y0 = min(_bounds(item['bbox'])[1] for item in rows[row_index]) - RECOVERY_PADDING_Y
            y1 = max(_bounds(item['bbox'])[3] for item in rows[row_index]) + RECOVERY_PADDING_Y
            x0 = regions[column_index][0] - RECOVERY_PADDING_X
            x1 = regions[column_index][1] + RECOVERY_PADDING_X
            crop = image[max(0, int(y0)):max(0, int(y1)), max(0, int(x0)):max(0, int(x1))]
            if crop.size == 0:
                continue
            text, confidence, method = _recognize_cell(crop, engine)
            if not _valid_recovery(text, confidence):
                continue
            grid[row_index][column_index] = text
            confidences[row_index][column_index] = round(confidence, 3)
            recovered.append({'row': row_index, 'column': column_index, 'text': text,
                              'confidence': round(confidence, 3), 'method': method})
    return recovered


def _render_markdown(headers: list[str], rows: list[list[str]]) -> str:
    def cell(value: str) -> str:
        return value.replace('|', '\\|') or ' '

    lines = ['| ' + ' | '.join(cell(value) for value in headers) + ' |',
             '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines.extend('| ' + ' | '.join(cell(value) for value in row) + ' |' for row in rows)
    return '\n'.join(lines)


def restore_table(labels: list[dict], *, page: int = 1, index: int = 1,
                  filename: str = '', document_id: str = '', image: np.ndarray | None = None,
                  engine=None) -> dict | None:
    grid, column_count, confidences = build_grid(labels)
    if not grid:
        return None
    recovered = recover_empty_cells(image, labels, grid, confidences, engine=engine) \
        if image is not None else []
    headers, body = grid[0], grid[1:]
    confidence = [item['confidence'] for item in labels]
    weak_cells = sum(1 for row_index, row in enumerate(body) for column_index, value in enumerate(row)
                     if value and confidences[row_index + 1][column_index] < CELL_CONFIDENCE_WARNING)
    return {'document_id': document_id, 'filename': filename, 'page': page,
            'table_index': index, 'title': f'第 {page} 页扫描表格 {index}',
            'headers': headers, 'rows': body, 'row_count': len(body),
            'column_count': column_count,
            'markdown': _render_markdown(headers, body),
            'mean_confidence': round(sum(confidence) / len(confidence), 3),
            'cell_confidence': confidences,
            'low_confidence_cells': weak_cells,
            'recovered_cells': len(recovered), 'recovery_details': recovered,
            'header_assumed': True, 'source': 'ocr_structure'}


def page_image(page, dpi: int = 200) -> np.ndarray:
    """Render a page once; label boxes and recovery crops must share these pixels."""
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n).copy()


def page_labels(page, dpi: int = 200) -> list[dict]:
    lines, _ = _engine()(page_image(page, dpi))
    return labels_from_boxes(lines)


def restore_scanned_tables(document_id: str, *, max_pages: int = MAX_PAGES) -> list[dict]:
    """OCR-only fallback used when the PDF has no native table structure."""
    from app.services.document_service import load_document, original_pdf_path

    document = load_document(document_id)
    filename = document.get('filename', '')
    extension = (document.get('extension') or filename.rsplit('.', 1)[-1]).lower()
    if extension not in {'.pdf', 'pdf'}:
        return []
    path, _ = original_pdf_path(document_id)
    tables = []
    with pymupdf.open(path) as pdf:
        for page_number, page in enumerate(pdf, 1):
            if page_number > max_pages:
                break
            if len(page.get_text('text').strip()) >= SCANNED_TEXT_LIMIT:
                continue
            image = page_image(page)
            lines, _ = _engine()(image)
            table = restore_table(labels_from_boxes(lines), image=image, page=page_number,
                                  index=len(tables) + 1, filename=filename,
                                  document_id=document_id)
            if table:
                tables.append(table)
    return tables

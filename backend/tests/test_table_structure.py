"""Row/column reconstruction from OCR boxes (deterministic fixtures, no OCR call)."""

import numpy as np
import pytest

from app.document.table import structure
from app.document.table.structure import (build_grid, cluster_rows, column_regions,
                                          labels_from_boxes, normalize_cell_text,
                                          recover_empty_cells, restore_table)


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def label(text, x0, y0, x1=100, y1=20, confidence=0.9):
    return {'text': text, 'confidence': confidence, 'bbox': box(x0, y0, x1, y1)}


THREE_BY_THREE = [
    label('年份', 10, 10, 60), label('收入', 200, 10, 260), label('利润', 400, 10, 460),
    label('2023', 10, 60, 60), label('120', 200, 60, 260), label('15', 400, 60, 460),
    label('2024', 10, 110, 60), label('150', 200, 110, 260), label('18', 400, 110, 460),
]


def test_rows_are_grouped_by_vertical_centre():
    rows = cluster_rows(THREE_BY_THREE)

    assert len(rows) == 3
    assert [item['text'] for item in rows[1]] == ['2023', '120', '15']


def test_column_regions_separate_real_gaps_only():
    regions = column_regions(THREE_BY_THREE)

    assert len(regions) == 3
    assert regions[0][0] == pytest.approx(10)
    assert regions[-1][0] == pytest.approx(400)


def test_grid_rebuilds_cells_in_reading_order():
    grid, column_count, confidences = build_grid(THREE_BY_THREE)

    assert column_count == 3
    assert grid[0] == ['年份', '收入', '利润']
    assert grid[2] == ['2024', '150', '18']


def test_restore_table_emits_markdown_and_flags_assumed_header():
    table = restore_table(THREE_BY_THREE, page=2, index=1, filename='scan.pdf', document_id='doc_1')

    assert table['row_count'] == 2
    assert table['column_count'] == 3
    assert table['header_assumed'] is True
    assert table['source'] == 'ocr_structure'
    assert table['markdown'].splitlines()[0] == '| 年份 | 收入 | 利润 |'
    assert table['markdown'].splitlines()[1] == '| --- | --- | --- |'
    assert table['mean_confidence'] == pytest.approx(0.9)


def test_single_row_or_single_column_is_not_a_table():
    assert restore_table([label('只有一行', 10, 10, 60), label('值', 200, 10, 260)]) is None
    assert restore_table([label('A', 10, 10, 60), label('B', 10, 60, 60)]) is None


def test_low_confidence_boxes_are_dropped():
    labels = labels_from_boxes([
        [box(10, 10, 60, 20), '可信', 0.9],
        [box(10, 40, 60, 50), '噪声', 0.3],
        [box(10, 70, 60, 80), '   ', 0.95],
    ])

    assert [item['text'] for item in labels] == ['可信']


def test_very_wide_gap_splits_columns_even_with_tall_boxes():
    labels = [label('A1', 10, 10, 90, 60), label('B1', 300, 10, 380, 60),
              label('A2', 10, 70, 90, 120), label('B2', 300, 70, 380, 120)]
    grid, column_count, _ = build_grid(labels)

    assert column_count == 2
    assert grid == [['A1', 'B1'], ['A2', 'B2']]


def test_table_qa_falls_back_to_restored_scanned_table(monkeypatch):
    from app.document.table import qa

    restored = restore_table(THREE_BY_THREE, page=3, filename='scan.pdf', document_id='doc_1')
    monkeypatch.setattr(qa, 'extract_tables', lambda document_id: [])
    monkeypatch.setattr('app.document.table.structure.restore_scanned_tables',
                        lambda document_id, **kwargs: [restored])

    answer = qa.query_table('doc_1', '2023 年的收入是多少')

    assert answer['value'] == '120'
    assert answer['sources'][0]['source'] == 'ocr_structure'
    assert 'confidence_warning' not in answer


def test_table_qa_flags_low_confidence_cell(monkeypatch):
    from app.document.table import qa

    restored = restore_table(THREE_BY_THREE, page=3, filename='scan.pdf', document_id='doc_1')
    restored['cell_confidence'][1][1] = 0.5
    monkeypatch.setattr(qa, 'extract_tables', lambda document_id: [])
    monkeypatch.setattr('app.document.table.structure.restore_scanned_tables',
                        lambda document_id, **kwargs: [restored])

    answer = qa.query_table('doc_1', '2023 年的收入是多少')

    assert answer['value'] == '120'
    assert 'OCR 置信度偏低' in answer['confidence_warning']


class FakeRecognizer:
    """Feed deterministic recognition results; never loads the real OCR engine."""

    def __init__(self, *results):
        self.results = list(results)

    def text_recognizer(self, images):
        if self.results:
            return [self.results.pop(0)], 0.0
        return [('', 0.0)], 0.0


def test_normalize_cell_text_folds_fullwidth_digits_and_spaces():
    assert normalize_cell_text('９') == '9'
    assert normalize_cell_text('１ ２') == '12'
    assert normalize_cell_text(' 2023 ') == '2023'


def test_recognize_cell_raises_confidence_when_views_agree():
    engine = FakeRecognizer(('９', 0.42), ('9', 0.55))
    crop = np.full((40, 120, 3), 255, dtype=np.uint8)

    text, confidence, method = structure._recognize_cell(crop, engine)

    assert text == '9'
    assert confidence == pytest.approx(0.55)
    assert method == 'agreed'


def test_recognize_cell_never_lets_second_view_overrule_primary():
    engine = FakeRecognizer(('9', 0.42), ('8', 0.99))
    crop = np.full((40, 120, 3), 255, dtype=np.uint8)

    text, confidence, method = structure._recognize_cell(crop, engine)

    assert text == '9'
    assert confidence == pytest.approx(0.42)
    assert method == 'rec_only'


def test_recovery_fills_only_empty_cells_and_keeps_low_confidence(monkeypatch):
    labels = [*THREE_BY_THREE[:3], THREE_BY_THREE[3], THREE_BY_THREE[5], *THREE_BY_THREE[6:]]
    grid, _, confidences = build_grid(labels)
    assert grid[1][1] == ''
    monkeypatch.setattr(structure, '_recognize_cell',
                        lambda crop, engine: ('120', 0.32, 'rec_only'))
    image = np.full((200, 500, 3), 255, dtype=np.uint8)

    details = recover_empty_cells(image, labels, grid, confidences, engine=object())

    assert grid[1] == ['2023', '120', '15']
    assert grid[2] == ['2024', '150', '18']
    assert confidences[1][1] == pytest.approx(0.32)
    assert len(details) == 1
    assert details[0]['row'] == 1 and details[0]['column'] == 1
    assert details[0]['method'] == 'rec_only'


@pytest.mark.parametrize('candidate', [
    ('', 0.0, ''),
    ('5', 0.05, 'rec_only'),        # below the accepted confidence floor
    ('###', 0.95, 'rec_only'),      # no alphanumeric content
    ('x' * 40, 0.9, 'rec_only'),    # implausibly long for a cell
])
def test_recovery_rejects_unreliable_candidates(monkeypatch, candidate):
    labels = [*THREE_BY_THREE[:3], THREE_BY_THREE[3], THREE_BY_THREE[5], *THREE_BY_THREE[6:]]
    grid, _, confidences = build_grid(labels)
    monkeypatch.setattr(structure, '_recognize_cell', lambda crop, engine: candidate)

    details = recover_empty_cells(np.full((200, 500, 3), 255, dtype=np.uint8),
                                  labels, grid, confidences, engine=object())

    assert details == []
    assert grid[1][1] == ''


def test_recovery_is_capped_to_bound_ocr_cost(monkeypatch):
    labels = [label(f'row{index}', 10, index * 50, 90, index * 50 + 20) for index in range(14)]
    labels.append(label('header', 300, 0, 380, 20))
    grid, _, confidences = build_grid(labels)
    monkeypatch.setattr(structure, '_recognize_cell',
                        lambda crop, engine: ('7', 0.4, 'rec_only'))

    details = recover_empty_cells(np.full((800, 500, 3), 255, dtype=np.uint8),
                                  labels, grid, confidences, engine=object())

    assert len(details) == structure.MAX_RECOVERY_CELLS


def test_restore_table_records_recovery_metadata_and_warning(monkeypatch):
    labels = [*THREE_BY_THREE[:3], THREE_BY_THREE[3], THREE_BY_THREE[5], *THREE_BY_THREE[6:]]
    monkeypatch.setattr(structure, '_recognize_cell',
                        lambda crop, engine: ('120', 0.32, 'agreed'))

    table = restore_table(labels, image=np.full((200, 500, 3), 255, dtype=np.uint8),
                          engine=object())

    assert table['rows'][0][1] == '120'
    assert table['recovered_cells'] == 1
    assert table['recovery_details'][0]['method'] == 'agreed'
    assert table['low_confidence_cells'] == 1


def test_restore_table_without_image_never_runs_recovery(monkeypatch):
    monkeypatch.setattr(structure, '_recognize_cell',
                        lambda crop, engine: pytest.fail('recovery must not run without an image'))

    table = restore_table(THREE_BY_THREE)

    assert table['recovered_cells'] == 0
    assert table['recovery_details'] == []

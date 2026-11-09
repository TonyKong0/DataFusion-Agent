import io

import numpy as np
import pytest
import pymupdf

from app.core.errors import AppError
from app.services import document_parser
from app.services.document_parser import parse_document


def test_csv_import_keeps_searchable_text_and_table_cells():
    parsed = parse_document(
        '年份,销售额\n2024,100\n2025,120\n'.encode(), 'revenue.csv')

    assert parsed.extension == '.csv'
    assert '2025 | 120' in parsed.pages[0]['text']
    assert parsed.tables[0]['headers'] == ['年份', '销售额']
    assert parsed.tables[0]['rows'] == [['2024', '100'], ['2025', '120']]


def test_xlsx_import_preserves_sheet_and_row_locator():
    openpyxl = pytest.importorskip('openpyxl')
    buffer = io.BytesIO()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = '年度收入'
    sheet.append(['年份', '收入'])
    sheet.append([2024, 100])
    sheet.append([2025, 120])
    workbook.save(buffer)

    parsed = parse_document(buffer.getvalue(), 'revenue.xlsx')

    assert parsed.pages[0]['locator'] == {'kind': 'xlsx', 'sheet': '年度收入',
                                         'row_start': 1, 'row_end': 3}
    assert parsed.tables[0]['sheet'] == '年度收入'
    assert parsed.tables[0]['headers'] == ['年份', '收入']
    assert parsed.tables[0]['rows'] == [['2024', '100'], ['2025', '120']]


def test_docx_import_indexes_paragraphs_and_structured_table():
    docx = pytest.importorskip('docx')
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph('年度收入报告')
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = '年份'
    table.rows[0].cells[1].text = '收入'
    row = table.add_row().cells
    row[0].text = '2025'
    row[1].text = '120'
    document.save(buffer)

    parsed = parse_document(buffer.getvalue(), 'report.docx')

    assert '年度收入报告' in parsed.pages[0]['text']
    assert parsed.tables[0]['headers'] == ['年份', '收入']
    assert parsed.tables[0]['rows'] == [['2025', '120']]


@pytest.mark.parametrize('filename,content', [
    ('notes.txt', '第一行\n第二行'.encode()),
    ('notes.md', '# 标题\n正文'.encode()),
])
def test_text_formats_keep_readable_content(filename, content):
    parsed = parse_document(content, filename)

    assert parsed.pages[0]['text']
    assert not parsed.tables


def test_unsupported_extension_has_actionable_error():
    with pytest.raises(AppError) as error:
        parse_document(b'not a word document', 'report.doc')

    assert getattr(error.value, 'code', None) == 'UNSUPPORTED_DOCUMENT_TYPE'


def test_direct_image_upload_runs_ocr_and_keeps_image_preview_metadata(monkeypatch):
    document = pymupdf.open()
    page = document.new_page(width=32, height=24)
    image_bytes = page.get_pixmap(alpha=False).tobytes('png')
    document.close()
    monkeypatch.setattr(document_parser, '_OCR_ENGINE', lambda image: (
        [([[0, 0], [10, 0], [10, 10], [0, 10]], 'Revenue', .99)], 0.01))

    parsed = parse_document(image_bytes, 'chart.png')

    assert parsed.pages[0]['text'] == 'Revenue'
    assert parsed.pages[0]['locator']['kind'] == 'image'
    assert parsed.preview_available is True

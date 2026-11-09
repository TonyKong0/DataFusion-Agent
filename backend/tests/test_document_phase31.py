import pymupdf
from app.document.pipeline import process_document
from app.document.models import DocumentNode


def test_pipeline_keeps_native_page_and_tree():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Normal PDF text')
        result = process_document(pdf.tobytes(), 'doc_test')
    assert result['pages'][0].text == 'Normal PDF text'
    assert result['pages'][0].metadata['ocr_used'] is False
    assert result['metadata']['native_pages'] == 1
    result['tree'].children.append(DocumentNode('Chapter', 1, 1))
    assert result['tree'].to_dict()['children'][0]['title'] == 'Chapter'

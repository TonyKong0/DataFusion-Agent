from app.document.models import DocumentPage
from app.document.structure.chunking import split_hierarchical


def test_chunks_keep_heading_path_and_do_not_cross_section():
    pages = [DocumentPage('d', 1, '第一章 总览\n简介内容\n1.1 方法\n参数为1200万元\n第二章 结果\n结论内容')]
    chunks = split_hierarchical(pages, 'd', 'a.pdf')
    assert len(chunks) == 3
    assert chunks[1]['heading_path'] == ['第一章 总览', '1.1 方法']
    assert '第二章' not in chunks[1]['text']
    assert chunks[2]['page'] == 1


def test_unstructured_pdf_keeps_legacy_fixed_chunking():
    pages = [DocumentPage('d', 1, 'x' * 1500)]
    chunks = split_hierarchical(pages, 'd', 'a.pdf')
    assert len(chunks) == 3
    assert len(chunks[0]['text']) == 800

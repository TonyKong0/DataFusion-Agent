from app.document.models import DocumentPage
from app.document.structure.toc_reconstructor import reconstruct


def test_mixed_numbering_recovers_parentage():
    pages = [DocumentPage('d', 1, '第一章 总论\n1.1 背景\n1.1.1 目标\n正文描述。\n第二章 方法\n2.1 数据')]
    headings, tree = reconstruct('d', pages)
    assert [h['level'] for h in headings] == [1, 2, 3, 1, 2]
    assert headings[2]['parent'] == '1.1 背景'
    assert tree['children'][0]['children'][0]['children'][0]['title'] == '1.1.1 目标'


def test_chinese_and_layout_headings():
    pages = [DocumentPage('d', 1, '一、研究背景\n（一）问题定义\n解释文字。',
              blocks=[{'text': '标题无编号', 'font_size': 20, 'bold': True},
                      {'text': '正文文字', 'font_size': 10}])]
    headings, _ = reconstruct('d', pages)
    assert [(h['title'], h['level']) for h in headings] == [('一、研究背景', 1), ('（一）问题定义', 2)]

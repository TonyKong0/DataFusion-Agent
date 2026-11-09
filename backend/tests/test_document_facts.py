from app.services.document_facts import author_answer, title_matches_question


def _document(identifier, filename, chunks):
    return {'document_id': identifier, 'filename': filename, 'status': 'indexed',
            'content': [{'chunk_id': f'{identifier}_{index}', 'page': page, 'text': text}
                        for index, (page, text) in enumerate(chunks)]}


def test_short_cover_title_and_author_are_cited():
    doc = _document('a', 'lesson-02.pdf', [(1, '课程模板\n岳阳楼记\n范仲淹')])

    result = author_answer([doc], '作者是谁？')

    assert result['answer'] == '《岳阳楼记》的作者是范仲淹。'
    assert result['sources'][0]['page'] == 1


def test_two_character_cover_title_is_supported():
    doc = _document('a', 'lesson.pdf', [(1, '诗经\n编者：张三')])

    assert title_matches_question(doc, '诗经的作者是谁？')
    assert author_answer([doc], '诗经的作者是谁？') is None


def test_two_selected_documents_use_explicit_work_title():
    first = _document('a', '醉翁亭记.pdf', [
        (1, '醉翁亭记\n教学课件'),
        (4, '宋代大散文家欧阳修写的传世之作《醉翁亭记》。')])
    second = _document('b', '岳阳楼记.pdf', [(1, '岳阳楼记\n范仲淹')])

    result = author_answer([first, second], '岳阳楼记的作者是谁？')

    assert result['answer'] == '《岳阳楼记》的作者是范仲淹。'
    assert [source['document_id'] for source in result['sources']] == ['b']


def test_missing_author_is_not_invented_from_section_heading():
    doc = _document('a', '新作品.pdf', [(1, '新作品\n第一章')])

    assert author_answer([doc], '作者是谁？') is None


def test_selected_materials_resolve_authors_per_document_without_titles_in_question():
    documents = [
        _document('a', '醉翁亭记.pdf', [(1, '醉翁亭记\n欧阳修')]),
        _document('b', '1范进中举.pdf', [(2, '今天一起走进吴敬梓的《范进中举》。'),
                                          (6, '吴敬梓（1701—1754），清代小说家。\n作者简介')]),
        _document('c', '行路难课件.pdf', [(3, '李白的《行路难》抒发了怀才不遇的心情。'),
                                         (4, '【李白】（701—762），唐代诗人。')]),
    ]

    result = author_answer(documents, '这几篇文章的作者是谁？')

    assert result['answer'] == ('《醉翁亭记》的作者是欧阳修。\n'
                                '《范进中举》的作者是吴敬梓。\n'
                                '《行路难》的作者是李白。')
    assert [source['document_id'] for source in result['sources']] == ['a', 'b', 'c']
    assert [source['page'] for source in result['sources']] == [1, 2, 3]


def test_missing_one_author_preserves_other_cited_answers():
    known = _document('a', '岳阳楼记.pdf', [(1, '岳阳楼记\n范仲淹')])
    unknown = _document('b', '无署名报告.pdf', [(1, '无署名报告\n项目背景与目标')])

    result = author_answer([known, unknown], '选中的材料作者分别是谁？')

    assert '《岳阳楼记》的作者是范仲淹。' in result['answer']
    assert '《无署名报告》：当前材料中未找到可确认的作者依据。' in result['answer']
    assert [source['document_id'] for source in result['sources']] == ['a']


def test_unrelated_writer_mention_is_not_treated_as_work_author():
    document = _document('a', '行路难.pdf', [(1, '诗作中多以醉时写的《行路难》为例。')])

    assert author_answer([document], '作者是谁？') is None


def test_model_fallback_requires_literal_author_in_the_cited_chunk():
    document = _document('a', '项目白皮书.pdf', [(3, '这份材料由张三丰编写完成。')])
    output = {'authors': [{'document_id': 'a', 'author': '张三丰', 'chunk_id': 'a_0'}]}

    result = author_answer([document], '作者是谁？', lambda *_: output)

    assert result['answer'] == '《项目白皮书》的作者是张三丰。'
    assert result['sources'][0]['page'] == 3
    assert author_answer([document], '作者是谁？', lambda *_: {
        'authors': [{'document_id': 'a', 'author': '李四', 'chunk_id': 'a_0'}]}) is None

from scripts.evaluate_conversation_memory import (
    chain_summary, score_agent_case, score_database_case, score_material_case,
)


def test_database_memory_turn_must_match_independent_query_oracle():
    passed, details = score_database_case(
        {'oracle': 'r_genres_top5'},
        {'success': True, 'table': 'genre', 'sql': 'SELECT Name FROM Genre ORDER BY Name LIMIT 5', 'columns': ['Name'],
         'rows': [['Reggae'], ['Rock'], ['R&B/Soul'], ['Rock And Roll']]},
        [['R&B/Soul'], ['Reggae'], ['Rock'], ['Rock And Roll']],
    )

    assert passed is False
    assert details['actual_values']
    extra_result = {'success': True, 'table': 'genre', 'sql': 'SELECT Name FROM Genre',
                    'rows': [['Reggae'], ['wrong extra row']]}
    assert score_database_case({'oracle': 'all_genres'}, extra_result, [['Reggae']])[0] is False


def test_material_memory_turn_requires_expected_page_and_answer_terms():
    case = {'page': 4, 'keywords': ['20', '100']}
    good = {'success': True, 'answer': '文件上限 20 MB，最多 100 页。',
            'sources': [{'page': 4, 'text': 'PDF 不超过 20 MB 和 100 页。'}]}
    wrong_page = {**good, 'sources': [{'page': 3, 'text': good['sources'][0]['text']}]}

    assert score_material_case(case, good)[0] is True
    assert score_material_case(case, wrong_page)[0] is False


def test_agent_memory_turn_requires_every_source_and_all_five_turns_to_pass():
    case = {'sources': ['database', 'document'], 'page': 3, 'keywords': ['25', '100'],
            'source_keywords': {'database': ['25'], 'document': ['100']},
            'database_oracle': 'count'}
    result = {'success': True, 'document_ids': ['doc-current'],
              'answer': '数据库有 25 种，PDF 上限为 100 行。',
              'evidence': [
                  {'source_type': 'database', 'content': {'rows': [[25]]},
                   'provenance': {'sql': 'SELECT COUNT(*) FROM Genre', 'tables': ['Genre']}},
                  {'source_type': 'document', 'content': '最多返回 100 行',
                   'provenance': {'page': 3, 'document_id': 'doc-current'}},
              ]}
    missing_document = {**result, 'evidence': result['evidence'][:1]}
    turns = [{'passed': True} for _ in range(5)]

    assert score_agent_case(case, result, 'doc-current', [[25]])[0] is True
    assert score_agent_case(case, missing_document, 'doc-current', [[25]])[0] is False
    wrong_document = {**result, 'evidence': [result['evidence'][0],
        {**result['evidence'][1], 'provenance': {'page': 3, 'document_id': 'doc-other'}}]}
    assert score_agent_case(case, wrong_document, 'doc-current', [[25]])[0] is False
    wrong_database_value = {**result, 'evidence': [
        {**result['evidence'][0], 'content': {'rows': [[24]]}}, result['evidence'][1]]}
    assert score_agent_case(case, wrong_database_value, 'doc-current', [[25]])[0] is False
    assert chain_summary(turns)['five_turn_passed'] is True
    assert chain_summary(turns[:-1] + [{'passed': False}])['five_turn_passed'] is False

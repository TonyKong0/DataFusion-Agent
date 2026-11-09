"""Golden-answer grading contracts (no LLM calls)."""

from scripts import evaluate_agent_v5


def _numeric_case(golden):
    return {'match_type': 'numeric', 'golden_numeric': golden}


def _contains_case(golden, golden_numeric=None, golden_alt=None):
    return {'match_type': 'contains', 'golden': golden,
            'golden_numeric': golden_numeric, 'golden_alt': golden_alt}


def test_reject_case_rewards_refusal():
    case = {'match_type': 'reject'}

    refused = evaluate_agent_v5.judge_answer('当前证据不足，无法确认答案。', case)
    assert refused['verdict'] == 'correct'

    invented = evaluate_agent_v5.judge_answer('审核阈值为 500 元。', case)
    assert invented['verdict'] == 'wrong'


def test_reject_case_treats_empty_answer_as_refusal():
    case = {'match_type': 'reject'}

    assert evaluate_agent_v5.judge_answer('', case)['verdict'] == 'correct'


def test_numeric_exact_match_without_doc_note_is_partial():
    judged = evaluate_agent_v5.judge_answer('数据库中共有 59 位客户。', _numeric_case(59))

    assert judged['verdict'] == 'partial'
    assert '未说明文档侧' in judged['reason']


def test_numeric_match_with_document_absence_is_correct():
    answer = '数据库中共有 59 位客户；文档未记录客户数量。'
    judged = evaluate_agent_v5.judge_answer(answer, _numeric_case(59))

    assert judged['verdict'] == 'correct'


def test_numeric_mismatch_is_wrong():
    judged = evaluate_agent_v5.judge_answer('数据库中共有 58 位客户。', _numeric_case(59))

    assert judged['verdict'] == 'wrong'


def test_numeric_tolerates_thousands_separators_and_one_percent():
    assert evaluate_agent_v5.judge_answer('共 1,567 条。', _numeric_case(1567))['verdict'] == 'partial'
    assert evaluate_agent_v5.judge_answer('共 59.5 条。', _numeric_case(59))['verdict'] == 'partial'
    assert evaluate_agent_v5.judge_answer('共 61 条。', _numeric_case(59))['verdict'] == 'wrong'


def test_contains_name_match_with_wrong_number_is_partial():
    answer = '数据库查询结果：标题：Minha Historia；total quantity：27.0。'
    judged = evaluate_agent_v5.judge_answer(answer, _contains_case('Minha Historia', 35))

    assert judged['verdict'] == 'partial'
    assert '数值' in judged['reason']


def test_contains_accepts_alternative_golden_name():
    judged = evaluate_agent_v5.judge_answer('歌曲为 The Trooper。', _contains_case('Dazed and Confused', 5, 'The Trooper'))

    assert judged['verdict'] == 'partial'


def test_contains_missing_name_is_wrong():
    judged = evaluate_agent_v5.judge_answer('A Cor Do Sol；total quantity：2.0。', _contains_case('Dazed and Confused', 5))

    assert judged['verdict'] == 'wrong'


def test_contains_full_match_with_document_absence_is_correct():
    answer = '数据库中销量最高的类型是 Rock（销量 835）；文档中无相关描述。'
    judged = evaluate_agent_v5.judge_answer(answer, _contains_case('Rock', 835))

    assert judged['verdict'] == 'correct'


def test_unknown_match_type_is_wrong_not_crash():
    judged = evaluate_agent_v5.judge_answer('任意回答', {'match_type': 'bogus'})

    assert judged['verdict'] == 'wrong'


def test_golden_file_covers_all_twelve_annotated_questions():
    cases = evaluate_agent_v5.load_golden_cases()

    assert len(cases) == 12
    assert all(case['match_type'] in ('numeric', 'contains', 'reject') for case in cases.values())
    assert sum(case['match_type'] == 'reject' for case in cases.values()) == 6

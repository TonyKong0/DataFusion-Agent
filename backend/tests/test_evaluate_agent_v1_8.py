"""v1.8 layered golden set, citation/faithfulness grading and cold/warm split.

All contracts here are offline: no LLM requests, no MySQL, no indexed material.
"""

from pathlib import Path

import pytest

from scripts import evaluate_agent_v5 as eval_v5

FIXTURE_SQL = ('SELECT c.FirstName FROM Customer AS c JOIN Invoice AS i '
               'ON c.CustomerId = i.CustomerId '
               'WHERE i.Total > (SELECT AVG(Total) FROM Invoice) LIMIT 100')
OVERREACH_ANSWER = '这些客户的消费总额均高于全体客户平均消费额。'


def _source(filename, text, page=1, locator=''):
    return {'source_name': filename, 'page': page, 'locator': locator, 'text': text}


def test_v18_draft_has_thirty_layered_cases():
    cases = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)

    assert len(cases) == 30
    assert {layer: sum(case['layer'] == layer for case in cases.values())
            for layer in eval_v5.LAYER_ORDER} == {'S1': 12, 'S2-A': 6, 'S2-B': 8, 'S2-C': 4}


def test_draft_is_explicitly_not_human_confirmed():
    meta = eval_v5.load_golden_meta(eval_v5.GOLDEN_DRAFT_V18)

    assert meta['status'] == 'pending_human_confirmation'
    assert meta['annotator'] is None
    assert eval_v5.golden_metrics_eligible(meta) is False
    assert eval_v5.golden_metrics_eligible({'status': 'human-confirmed'}) is True
    assert eval_v5.golden_metrics_eligible({'status': 'human-confirmed'}, 'FileNotFoundError') is False


def test_default_v17_golden_set_stays_human_confirmed():
    assert eval_v5.golden_metrics_eligible(eval_v5.load_golden_meta()) is True
    assert len(eval_v5.load_golden_cases()) == 12


def test_document_fact_cases_carry_citation_criteria():
    cases = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)
    document_facts = [case for case in cases.values() if case['layer'] == 'S2-B']

    assert len(document_facts) == 8
    for case in document_facts:
        assert case['expected_citation']
        assert case['citation_facts']
        assert case['forbidden_claims']
        assert case['target_document'] in eval_v5.EVALUATION_MATERIALS


def test_s1_anchor_questions_match_v17_wording():
    v17 = eval_v5.load_golden_cases()
    v18 = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)
    anchors = [case for case in v18.values() if case['layer'] == 'S1']

    assert {case['question'] for case in anchors} == set(v17)
    assert all('历史值' in case['annotation_origin'] for case in anchors)


def test_every_case_has_its_grading_contract():
    for case in eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18).values():
        assert case['match_type'] in ('numeric', 'contains', 'reject', 'reject*')
        assert case['annotation_origin']
        assert isinstance(case['forbidden_claims'], list)


def test_three_text_materials_are_fixed_and_exclusions_are_documented():
    assert eval_v5.EVALUATION_MATERIALS == (
        '07_store_faq.txt', '08_chinook_data_dictionary.md', '04_invoice_review_example.docx')
    assert '02_service_policy_example.pdf' in eval_v5.EXCLUDED_MATERIALS_NOTE
    assert '03_ocr-sign.png' in eval_v5.EXCLUDED_MATERIALS_NOTE


def test_citation_supported_when_expected_material_and_fact_are_present():
    case = {'expected_citation': '07_store_faq.txt 第 3 问',
            'citation_facts': ['复核筛选条件']}
    sources = [_source('07_store_faq.txt', '这个阈值只是复核筛选条件，退款仍需独立核对。',
                       locator='第 3 问')]

    judged = eval_v5.judge_citation('文档第 1 页说明该阈值仅为复核筛选条件。', case, sources)

    assert judged['citation_supported'] is True
    assert judged['matched_document'] is True
    assert judged['fact_hits'] == ['复核筛选条件']


def test_citation_wrong_material_is_unsupported():
    case = {'expected_citation': '07_store_faq.txt 第 3 问', 'citation_facts': ['复核筛选条件']}
    sources = [_source('08_chinook_data_dictionary.md', '虚构规则，不是数据库约束。')]

    judged = eval_v5.judge_citation('文档第 1 页提到虚构规则。', case, sources)

    assert judged['citation_supported'] is False
    assert judged['matched_document'] is False


def test_citation_right_material_without_fact_is_unsupported():
    case = {'expected_citation': '04_invoice_review_example.docx 判读规则段',
            'citation_facts': ['重点复核队列']}
    sources = [_source('04_invoice_review_example.docx', 'Invoice.Total 为金额字段。')]

    judged = eval_v5.judge_citation('文档第 1 页：Invoice.Total 为金额字段。', case, sources)

    assert judged['citation_supported'] is False
    assert judged['fact_hits'] == []


def test_citation_without_any_reference_is_no_claim():
    case = {'expected_citation': '07_store_faq.txt 第 3 问', 'citation_facts': ['复核筛选条件']}

    judged = eval_v5.judge_citation('退款已经批准。', case, [])

    assert judged['citation_supported'] == 'no_claim'


def test_cases_without_citation_criterion_stay_out_of_denominator():
    judged = eval_v5.judge_citation('任意回答', {}, [_source('07_store_faq.txt', '任意')])

    assert judged['citation_supported'] is None


def test_forbidden_claim_makes_answer_unfaithful():
    case = {'forbidden_claims': ['自动退款', '代表退款批准']}

    judged = eval_v5.judge_faithfulness('金额超过 5 美元，自动退款。', case)

    assert judged['faithful'] is False
    assert judged['matched_forbidden'] == ['自动退款']


def test_clean_answer_is_faithful():
    case = {'forbidden_claims': ['自动退款', '代表退款批准']}

    judged = eval_v5.judge_faithfulness('该阈值仅为复核筛选条件，退款需独立核对。', case)

    assert judged['faithful'] is True


def test_row_level_sql_overreach_is_detected_in_faithfulness():
    case = {'forbidden_claims': ['消费总额']}

    judged = eval_v5.judge_faithfulness(OVERREACH_ANSWER, case, [FIXTURE_SQL])

    assert judged['faithful'] is False
    assert judged['sql_overreach'] is True


def test_faithfulness_without_criteria_stays_out_of_denominator():
    assert eval_v5.judge_faithfulness('任意回答', {})['faithful'] is None


def test_clarification_cases_require_clarification_markers():
    for case in eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18).values():
        if case['layer'] == 'S2-C' and case['match_type'] == 'reject*':
            assert eval_v5.judge_answer('请明确数据源或材料范围。', case)['verdict'] == 'correct'
            assert eval_v5.judge_answer('数据库中共有 59 位客户。', case)['verdict'] == 'wrong'


def test_reject_marker_semantics_are_unchanged():
    case = {'match_type': 'reject'}

    assert eval_v5.judge_answer('当前证据不足，无法确认答案。', case)['verdict'] == 'correct'
    assert eval_v5.judge_answer('审核阈值为 500 元。', case)['verdict'] == 'wrong'


def test_layered_sample_covers_every_layer_first():
    cases = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)

    sample = eval_v5._layered_sample(cases, 4)

    assert {case['layer'] for case in sample} == set(eval_v5.LAYER_ORDER)


def test_layered_sample_can_take_all_thirty_cases():
    cases = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)

    sample = eval_v5._layered_sample(cases, 30)

    assert len(sample) == 30
    assert len({case['question'] for case in sample}) == 30
    assert sum(case['layer'] == 'S2-B' for case in sample) == 8


def _rows():
    return [{'question': f'q{i}', 'phase': 'cold' if i == 0 else 'warm',
             'latency_ms': value} for i, value in enumerate([54600, 3000, 4000, 5000, 6000])]


def test_latency_breakdown_separates_cold_start_from_warm_distribution():
    summary = eval_v5.summarize_latencies(_rows())

    assert summary['cold']['count'] == 1
    assert summary['cold_start_latency_ms'] == 54600
    assert summary['cold_start_case'] == 'q0'
    assert summary['warm']['count'] == 4
    assert summary['warm']['mean_ms'] == 4500
    assert summary['warm']['p50_ms'] == 4000
    # P95 keeps the project's existing int(.95 * (n - 1)) index convention.
    assert summary['warm']['p95_ms'] == 5000
    assert summary['all']['mean_ms'] == 14520


def test_empty_latency_rows_have_no_fabricated_numbers():
    summary = eval_v5.summarize_latencies([])

    assert summary['cold_start_latency_ms'] is None
    assert summary['warm']['mean_ms'] is None
    assert summary['warm']['p95_ms'] is None


def test_golden_argument_is_available_and_defaults_to_none():
    parser = eval_v5.build_parser()

    assert parser.parse_args([]).golden is None
    assert parser.parse_args(['--golden', 'tests/golden_answers_v1.8.draft.json']).golden == Path(
        'tests/golden_answers_v1.8.draft.json')


def test_live_mode_still_requires_positive_api_cap():
    with pytest.raises(ValueError):
        eval_v5.run_live(0)

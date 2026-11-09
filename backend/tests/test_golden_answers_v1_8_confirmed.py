"""Guard the human-confirmed v1.8 golden set and its grading denominator.

The user confirmed all 30 rows on 2026-11-08.  These tests make the confirmed
criteria immutable by accident: the confirmed file must stay byte-equivalent
to the pre-filled draft in every case field, and the answer-accuracy denominator
must match the annotated 26 / 4 split.
"""

from scripts import evaluate_agent_v5 as eval_v5


def test_confirmed_set_is_metrics_eligible():
    meta = eval_v5.load_golden_meta(eval_v5.GOLDEN_CONFIRMED_V18)

    assert meta['status'] == 'human-confirmed'
    assert meta['annotator']
    assert meta['annotated_at']
    assert 'warning' not in meta
    assert eval_v5.golden_metrics_eligible(meta) is True


def test_confirmed_cases_are_identical_to_the_reviewed_draft():
    """No case field may be changed after human confirmation."""
    confirmed = eval_v5.load_golden_cases(eval_v5.GOLDEN_CONFIRMED_V18)
    draft = eval_v5.load_golden_cases(eval_v5.GOLDEN_DRAFT_V18)

    assert confirmed == draft
    assert len(confirmed) == 30


def test_confirmed_set_keeps_the_annotated_layer_split():
    cases = eval_v5.load_golden_cases(eval_v5.GOLDEN_CONFIRMED_V18)

    assert {layer: sum(case['layer'] == layer for case in cases.values())
            for layer in eval_v5.LAYER_ORDER} == {'S1': 12, 'S2-A': 6, 'S2-B': 8, 'S2-C': 4}
    assert sum(case['layer'] != 'S2-C' for case in cases.values()) == 26
    assert sum(bool(case.get('expected_citation')) for case in cases.values()) == 8
    assert all(case['expected_citation'] for case in cases.values()
               if case['layer'] == 'S2-B')


def test_draft_stays_ineligible_after_confirmation():
    """The draft is retained as provenance, never as a measurement source."""
    draft_meta = eval_v5.load_golden_meta(eval_v5.GOLDEN_DRAFT_V18)

    assert draft_meta['status'] == 'pending_human_confirmation'
    assert draft_meta['annotator'] is None
    assert eval_v5.golden_metrics_eligible(draft_meta) is False


def test_s2c_cases_stay_out_of_answer_accuracy_denominator():
    rows = [
        {'question': 'a', 'layer': 'S1', 'verdict': 'correct'},
        {'question': 'b', 'layer': 'S2-A', 'verdict': 'partial'},
        {'question': 'c', 'layer': 'S2-B', 'verdict': 'wrong'},
        {'question': 'd', 'layer': 'S2-C', 'verdict': 'correct'},
        {'question': 'e', 'layer': None, 'verdict': 'correct'},  # legacy v1.7 run
        {'question': 'f', 'layer': 'S2-C', 'verdict': None},
    ]

    kept = eval_v5._answer_accuracy_rows(rows)

    assert [row['question'] for row in kept] == ['a', 'b', 'c', 'e']


def test_numeric_and_contains_cases_already_reward_document_absence():
    """Pre-change baseline: explicit 'document does not record X' is graded correct."""
    numeric = {'match_type': 'numeric', 'golden_numeric': 59}
    contains = {'match_type': 'contains', 'golden': 'Rock', 'golden_numeric': 835}

    assert eval_v5.judge_answer('共有 59 位客户，文档未记录客户数。', numeric)['verdict'] == 'correct'
    assert eval_v5.judge_answer('共有 59 位客户。', numeric)['verdict'] == 'partial'
    assert eval_v5.judge_answer('销量最高的是 Rock，835，文档无相关描述。', contains)['verdict'] == 'correct'
    assert eval_v5.judge_answer('销量最高的是 Rock，835。', contains)['verdict'] == 'partial'


def test_v18_reject_cases_still_use_generic_reject_markers():
    """Pre-change baseline for the post-v1.8 iteration.

    The six S1 reject cases currently accept a generic refusal; they do not yet
    require the answer to state that the *document* lacks the information.  This
    is the behaviour the user asked to change in a later iteration, so the
    baseline is pinned here for a clean before/after comparison.
    """
    case = {'match_type': 'reject'}

    assert eval_v5.judge_answer('当前证据不足，无法确认答案。', case)['verdict'] == 'correct'
    assert eval_v5.judge_answer('所检索材料中未记载审核阈值，无法据此作答。', case)['verdict'] == 'correct'
    assert eval_v5.judge_answer('审核阈值为 500 元。', case)['verdict'] == 'wrong'

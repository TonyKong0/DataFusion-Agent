from scripts.evaluate_retail_benchmark import (
    DEFAULT_TOTAL_TOKEN_BUDGET,
    evaluate_output,
    parse_args,
    rows_match,
)


def test_clarification_without_table_is_a_structured_failure():
    passed, error = evaluate_output({
        'need_clarification': True, 'table': None, 'rows': [],
        'answer': '需要补充信息',
    }, 'retail_transaction', [[490]])

    assert passed is False
    assert error == 'NEED_CLARIFICATION'


def test_missing_table_without_clarification_does_not_raise():
    passed, error = evaluate_output({'table': None, 'rows': []},
                                   'retail_transaction', [[490]])

    assert passed is False
    assert error == 'MISSING_TABLE'


def test_row_order_is_ignored_but_a_tied_cutoff_item_is_not():
    expected = [['21212', 150.0], ['22866', 144.0]]
    reordered = [['22866', 144.0], ['21212', 150.0]]
    different_tie = [['21212', 150.0], ['37449', 144.0]]

    assert rows_match(reordered, expected, order_matters=False)
    assert not rows_match(different_tie, expected, order_matters=False)


def test_evaluation_respects_cases_that_require_ordered_results():
    passed, error = evaluate_output(
        {'table': 'retail_transaction', 'rows': [['22866', 144.0], ['21212', 150.0]]},
        'retail_transaction', [['21212', 150.0], ['22866', 144.0]],
        order_matters=True,
    )

    assert passed is False
    assert error == 'RESULT_MISMATCH'


def test_evaluation_budget_defaults_to_two_million_tokens_without_request_cap():
    args = parse_args(['--live'])

    assert args.max_total_tokens == DEFAULT_TOTAL_TOKEN_BUDGET == 2_000_000
    assert args.max_api_requests is None


def test_evaluation_budgets_can_be_adjusted_independently():
    args = parse_args([
        '--live', '--max-total-tokens', '250000', '--max-api-requests', '240',
    ])

    assert args.max_total_tokens == 250_000
    assert args.max_api_requests == 240

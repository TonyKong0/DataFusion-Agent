import pytest

from app.agent.budget import current_budget, estimate_tokens, request_budget
from app.core.errors import AppError


def test_context_budget_counts_system_and_user_prompt_together():
    with request_budget(2, 10, 1000):
        with pytest.raises(AppError) as caught:
            current_budget().consume('x' * 3000, system='系统指令')

    assert caught.value.code == 'CONTEXT_BUDGET_EXCEEDED'


def test_context_budget_reports_peak_and_actual_provider_prompt_usage():
    with request_budget(3, 10, 5000) as budget:
        budget.consume('{"question":"问题"}', system='系统提示')
        budget.record_usage(37, 11)
        budget.consume('short', system='a longer system prompt')
        budget.record_usage(51, 9)

    usage = budget.context_usage()
    assert usage['budget_tokens'] == 5000
    assert usage['measurement'] == 'provider'
    assert usage['used_tokens'] == 51
    assert usage['remaining_tokens'] == 4949
    assert usage['total_prompt_tokens'] == 88
    assert usage['total_completion_tokens'] == 20
    assert usage['breakdown']['system_prompt'] > 0


def test_context_budget_uses_estimate_when_provider_omits_usage():
    with request_budget(2, 10, 1000) as budget:
        budget.consume('中文问题', system='系统指令')

    usage = budget.context_usage()
    assert usage['measurement'] == 'estimate'
    assert usage['used_tokens'] == estimate_tokens('系统指令中文问题')
    assert usage['remaining_tokens'] == 1000 - usage['used_tokens']


def test_nested_request_budgets_share_the_full_sequence_request_limit():
    with request_budget(2, 10, 5000) as outer:
        outer.consume('first')
        with request_budget(9, 40, 50000) as nested:
            assert nested is outer
            nested.consume('second')
            with pytest.raises(AppError) as caught:
                nested.consume('third')

    assert caught.value.code == 'LLM_BUDGET_EXCEEDED'


def test_nested_request_keeps_per_turn_limit_inside_larger_evaluation_cap():
    with request_budget(20, 10, 5000) as evaluation_budget:
        with request_budget(2, 10, 5000):
            evaluation_budget.consume('one')
            evaluation_budget.consume('two')
            with pytest.raises(AppError) as caught:
                evaluation_budget.consume('three')
        with request_budget(2, 10, 5000):
            evaluation_budget.consume('next-turn-one')

    assert caught.value.code == 'LLM_BUDGET_EXCEEDED'
    assert evaluation_budget.used == 3


def test_total_token_budget_reserves_prompt_and_maximum_completion_before_call():
    with request_budget(10, 10, 1000, max_total_tokens=20) as budget:
        budget.consume('hello', max_completion_tokens=10)
        with pytest.raises(AppError) as caught:
            budget.consume('world', max_completion_tokens=10)

    assert caught.value.code == 'LLM_TOKEN_BUDGET_EXCEEDED'
    assert budget.token_budget_usage() == {
        'maximum_tokens': 20,
        'provider_reported_tokens': 0,
        'reserved_tokens_without_usage': 12,
        'budgeted_tokens': 12,
        'remaining_tokens': 8,
        'exceeded': False,
    }


def test_reported_usage_releases_unused_reservation_for_next_call():
    with request_budget(10, 10, 1000, max_total_tokens=21) as budget:
        budget.consume('hello', max_completion_tokens=10)
        budget.record_usage(2, 5)
        budget.consume('world', max_completion_tokens=10)

    usage = budget.token_budget_usage()
    assert usage['provider_reported_tokens'] == 7
    assert usage['reserved_tokens_without_usage'] == 12
    assert usage['budgeted_tokens'] == 19
    assert usage['remaining_tokens'] == 2


def test_nested_request_budgets_share_total_token_cap():
    with request_budget(10, 10, 1000, max_total_tokens=15) as budget:
        with request_budget(5, 10, 1000):
            budget.consume('hello', max_completion_tokens=10)
            with pytest.raises(AppError) as caught:
                budget.consume('next', max_completion_tokens=10)

    assert caught.value.code == 'LLM_TOKEN_BUDGET_EXCEEDED'


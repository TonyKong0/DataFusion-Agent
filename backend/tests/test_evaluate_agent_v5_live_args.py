"""Argument and mode contracts for the agent evaluation script (no LLM calls)."""

import pytest

from scripts import evaluate_agent_v5


def test_default_mode_stays_offline_and_needs_no_cap():
    args = evaluate_agent_v5.build_parser().parse_args([])

    assert args.live is False
    assert args.max_api_requests == 0


def test_live_mode_requires_a_positive_api_cap():
    with pytest.raises(SystemExit) as error:
        evaluate_agent_v5.main(['--live', '--max-api-requests', '0'])

    assert error.value.code == 2


def test_live_mode_rejects_a_missing_cap():
    with pytest.raises(SystemExit):
        evaluate_agent_v5.main(['--live'])


def test_run_live_refuses_zero_cap_directly():
    with pytest.raises(ValueError):
        evaluate_agent_v5.run_live(0)


def test_offline_result_reports_zero_live_requests():
    result = evaluate_agent_v5.run()

    assert result['live_answer_accuracy'] is None
    assert result['synthetic_avg_llm_calls'] == 0
    assert result['routing_accuracy'] is not None

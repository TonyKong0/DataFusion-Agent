from tests.evaluate_schema_v3 import evaluate as evaluate_schema
from tests.evaluate_multitable_v3 import evaluate as evaluate_multitable


def test_fifty_schema_cases_have_real_candidates_and_selections():
    result = evaluate_schema()
    assert result['cases'] == 50
    assert result['metrics']['table_recall_at_5'] >= 0.9
    assert result['metrics']['column_recall_at_10'] >= 0.9
    assert result['metrics']['exact_match'] >= 0.8


def test_fifty_multitable_cases_have_real_paths_and_valid_reference_sql():
    result = evaluate_multitable(live=False)
    assert result['cases'] == 50
    assert result['categories'] == {'two_table': 20, 'three_table': 15,
                                    'aggregation': 10, 'complex': 5}
    assert result['metrics']['intent_detected'] >= 0.9
    assert result['metrics']['join_path_correct'] >= 0.9
    assert result['metrics']['reference_valid'] == 1.0

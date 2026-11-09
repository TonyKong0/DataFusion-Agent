from tests.evaluate_document_v4 import evaluate


def test_controlled_v4_benchmark_has_required_case_counts():
    results = evaluate()
    assert results['formula']['metrics']['count'] >= 20
    assert results['headings']['metrics']['documents'] >= 10
    assert results['complexity']['metrics']['documents'] >= 20
    assert results['formula']['metrics']['calculation_accuracy'] == 1

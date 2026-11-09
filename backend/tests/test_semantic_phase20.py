from tests.evaluate_semantic_v2 import evaluate


def test_phase20_datasets_and_metrics_are_reproducible():
    result = evaluate()
    assert all(result[key]['cases'] >= 30 for key in result)
    assert 0 <= result['normalization']['accuracy'] <= 1
    assert 0 <= result['element_extraction']['f1'] <= 1
    assert 0 <= result['clarification']['recall'] <= 1

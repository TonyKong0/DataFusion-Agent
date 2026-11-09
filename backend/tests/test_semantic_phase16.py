from app.semantic.element_merger import merge_elements
from app.semantic.models import Element


def test_merge_duplicate_prefers_exact_dictionary():
    result = merge_elements([
        Element('filter', 'Rock', 'rule', 0.95, name='genre'),
        Element('filter', 'Rock', 'dictionary', 1.0, name='genre'),
    ])
    assert len(result['elements']) == 1
    assert result['elements'][0].source == 'dictionary'
    assert result['elements'][0].confidence == 1.0
    assert not result['conflicts']


def test_conflict_retains_both_and_lowers_confidence():
    result = merge_elements([
        Element('filter', 'Rock', 'dictionary', 1.0, name='genre'),
        Element('filter', 'Pop', 'llm', 0.8, name='genre'),
    ])
    assert result['conflicts'] == [{'type': 'filter', 'name': 'genre', 'values': ['Rock', 'Pop']}]
    assert {item.canonical_value for item in result['elements']} == {'Rock', 'Pop'}
    assert all(item.confidence == 0.6 for item in result['elements'])


def test_different_filter_names_do_not_conflict():
    result = merge_elements([
        Element('filter', 'USA', 'dictionary', 1.0, name='country'),
        Element('filter', 'Rock', 'dictionary', 1.0, name='genre'),
    ])
    assert len(result['elements']) == 2
    assert result['conflicts'] == []

import json
from pathlib import Path


def test_fixed_ohr_subset_covers_five_source_categories_with_unique_ids():
    path = Path(__file__).parent / 'cases' / 'ohr_bench_subset.json'
    cases = json.loads(path.read_text(encoding='utf-8'))

    assert len(cases) == 15
    assert len({item['id'] for item in cases}) == 15
    assert {item['evidence_source'] for item in cases} == {
        'text', 'table', 'formula', 'chart', 'reading_order'}
    assert all(len([case for case in cases if case['evidence_source'] == source]) == 3
               for source in ('text', 'table', 'formula', 'chart', 'reading_order'))
    assert all(item['answer'] and item['pages'] and min(item['pages']) >= 1 for item in cases)

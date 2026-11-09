import pytest
from app.evidence.fusion import fuse_evidence


def ev(kind, value, key='审核阈值', index=1):
    return {'evidence_id': f'ev_{index}', 'source_type': kind, 'source_name': kind,
            'content': value, 'confidence': .9, 'fact_key': key, 'provenance': {}}


@pytest.mark.parametrize('value', [0, 1, 5, 10, 50, 100, 500, 1000])
def test_agreement(value):
    result = fuse_evidence([ev('document', value), ev('database', value, index=2)],
                           ['document', 'database'])
    assert result['sufficient'] and not result['conflicts']


@pytest.mark.parametrize('values', [(500, 600), (1, 2), (100, 99), (0, 1), (42, 43), (5000, 6000)])
def test_conflicts_are_explicit(values):
    result = fuse_evidence([ev('document', values[0]), ev('database', values[1], index=2)],
                           ['document', 'database'])
    assert not result['sufficient']
    assert result['conflicts'][0]['resolution'] == 'unresolved'
    assert result['conflicts'][0]['evidence_ids'] == ['ev_1', 'ev_2']


@pytest.mark.parametrize('source', ['database', 'document', 'formula'])
def test_missing_source(source):
    result = fuse_evidence([ev('document', 500)], [source, 'database'])
    assert not result['sufficient']
    assert result['missing']


@pytest.mark.parametrize('key', ['订单数', '销量', '客户数'])
def test_complementary_facts_not_conflict(key):
    result = fuse_evidence([ev('document', 500, '审核阈值'), ev('database', 12, key, 2)],
                           ['document', 'database'])
    assert result['sufficient'] and not result['conflicts']

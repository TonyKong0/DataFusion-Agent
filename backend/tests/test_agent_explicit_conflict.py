from app.agent.service import _mark_explicit_comparison
from app.agent.models import ToolResult
from app.evidence.fusion import fuse_evidence


def test_explicit_same_metric_detects_real_cross_source_disagreement():
    evidence = [{'evidence_id': 'db', 'source_type': 'database', 'step_id': 'step_1',
                 'content': {'columns': ['value'], 'rows': [[600]]}},
                {'evidence_id': 'doc', 'source_type': 'document', 'step_id': 'step_2',
                 'content': '审核阈值为 500 元'}]
    results = {'step_1': ToolResult('database_query', True, {'columns': ['value'], 'rows': [[600]]}),
               'step_2': ToolResult('document_search', True, {'answer': '审核阈值为 500 元'})}
    _mark_explicit_comparison('数据库审核阈值和文档审核阈值是否一致？', evidence, results)
    fusion = fuse_evidence(evidence, ['database', 'document'])
    assert fusion['conflicts'][0]['values'] == [600, 500]


def test_parallel_unrelated_counts_not_compared():
    evidence = [{'evidence_id': 'db', 'source_type': 'database', 'step_id': 'step_1',
                 'content': {'columns': ['value'], 'rows': [[600]]}},
                {'evidence_id': 'doc', 'source_type': 'document', 'step_id': 'step_2',
                 'content': '人数为 500'}]
    _mark_explicit_comparison('数据库里有多少客户，文档里记录了多少？', evidence, {})
    assert not fuse_evidence(evidence, ['database', 'document'])['conflicts']

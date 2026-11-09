from app.document.versioning import comparator


def test_version_added_deleted_modified_with_pages(monkeypatch):
    docs = {
        'old': {'document_id': 'old', 'filename': 'v1.pdf', 'content': [
            {'chunk_id': 'a', 'page': 1, 'heading_path': ['审核规则'], 'text': '阈值为 500'},
            {'chunk_id': 'b', 'page': 2, 'heading_path': ['旧章节'], 'text': '旧内容'}]},
        'new': {'document_id': 'new', 'filename': 'v2.pdf', 'content': [
            {'chunk_id': 'c', 'page': 3, 'heading_path': ['审核规则'], 'text': '阈值为 600'},
            {'chunk_id': 'd', 'page': 4, 'heading_path': ['新章节'], 'text': '新内容'}]},
    }
    monkeypatch.setattr(comparator, 'load_document', lambda key: docs[key])
    result = comparator.compare('old', 'new')
    assert result['counts'] == {'added': 1, 'deleted': 1, 'modified': 1}
    modified = next(item for item in result['changes'] if item['change_type'] == 'modified')
    assert 'numeric_change' in modified['change_details']
    assert modified['old_source']['page'] == 1 and modified['new_source']['page'] == 3

from app.semantic.element_extractor import extract_elements
from app.semantic.semantic_validator import validate_semantics
from app.services import nl2sql_service


def _validate(question):
    return validate_semantics(question, extract_elements(question))


def test_simple_question_is_valid():
    assert _validate('前10个客户')['valid'] is True


def test_missing_entity_requires_clarification(monkeypatch):
    monkeypatch.setattr('app.semantic.element_extractor.chat', lambda *args, **kwargs: '{"elements":[]}')
    assert _validate('查 Alex')['missing'] == ['entity']


def test_missing_time_range_requires_clarification():
    assert 'time_range' in _validate('客户增长率是多少')['missing']


def test_ambiguous_entities_and_join_rejected():
    result = _validate('客户和员工的关联')
    assert result['need_clarification'] is True
    assert 'multi_table' in result['unsupported']


def test_unsupported_cross_table_filter_rejected():
    assert 'filter:genre' in _validate('Rock 歌曲')['unsupported']


def test_low_confidence_requires_clarification(monkeypatch):
    monkeypatch.setattr('app.semantic.element_extractor.chat', lambda *args, **kwargs:
                        '{"elements":[{"type":"metric","raw_value":"卖得比较猛","canonical_value":"sales"}]}')
    assert _validate('卖得比较猛的歌曲')['low_confidence'] is True


def test_no_sql_when_clarification_needed(monkeypatch):
    monkeypatch.setattr(nl2sql_service, 'load_schema', lambda: (_ for _ in ()).throw(AssertionError('schema loaded')))
    result = nl2sql_service.query('客户增长率是多少')
    assert result['need_clarification'] is True
    assert result['sql'] is None
    assert all(item['name'] != 'sql_generate' for item in result['trace'])

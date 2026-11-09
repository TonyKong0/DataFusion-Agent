import pytest

from app.semantic.config_loader import load_config
from app.semantic.models import Element


def test_element_is_serializable():
    element = Element(type='filter', name='country', raw_value='美国',
                      canonical_value='USA', source='dictionary', confidence=1.0)
    assert element.to_dict() == {'type': 'filter', 'name': 'country',
                                 'raw_value': '美国', 'canonical_value': 'USA',
                                 'source': 'dictionary', 'confidence': 1.0}


def test_six_configured_types():
    assert set(load_config('element_types.yaml')['elements']) == {
        'entity', 'filter', 'metric', 'sort', 'limit', 'time',
    }


def test_type_is_loaded_from_config(monkeypatch):
    from app.semantic import models
    original = models.load_config
    monkeypatch.setattr(models, 'load_config', lambda name: {'elements': {'custom': {}}}
                        if name == 'element_types.yaml' else original(name))
    assert Element('custom', 'value', 'rule', 0.95).type == 'custom'


@pytest.mark.parametrize('type,source,confidence', [
    ('unknown', 'rule', 0.95), ('entity', 'unknown', 0.95),
    ('entity', 'rule', -0.1), ('entity', 'rule', 1.1),
])
def test_invalid_element_rejected(type, source, confidence):
    with pytest.raises(ValueError):
        Element(type, 'Customer', source, confidence)

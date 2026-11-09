"""Phase 11 proves the V2 semantic boundary can load in isolation."""

from dataclasses import asdict
from importlib import import_module

import pytest

from app.semantic import SemanticRequest
from app.semantic.config_loader import CONFIG_FILES, load_config


@pytest.mark.parametrize('module', [
    'models', 'normalizer', 'element_extractor', 'alias_resolver',
    'semantic_validator', 'clarification_manager', 'config_loader',
])
def test_semantic_modules_import(module):
    assert import_module(f'app.semantic.{module}')


def test_semantic_request_keeps_original_question():
    assert asdict(SemanticRequest('一共有多少个艺术家')) == {
        'original_question': '一共有多少个艺术家',
    }


@pytest.mark.parametrize('filename', sorted(CONFIG_FILES))
def test_semantic_configs_load_as_mappings(filename):
    assert isinstance(load_config(filename), dict)


def test_unknown_config_is_rejected():
    with pytest.raises(ValueError, match='Unknown semantic config'):
        load_config('../.env')

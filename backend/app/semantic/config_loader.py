"""Read the four V2 semantic YAML files without executing arbitrary content."""

from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'
CONFIG_FILES = frozenset({
    'element_types.yaml',
    'aliases.yaml',
    'semantic_rules.yaml',
    'clarification_rules.yaml',
})


def load_config(filename: str) -> dict[str, Any]:
    """Load a known semantic config file as a mapping."""
    if filename not in CONFIG_FILES:
        raise ValueError(f'Unknown semantic config: {filename}')
    data = yaml.safe_load((CONFIG_DIR / filename).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Semantic config must be a mapping: {filename}')
    return data

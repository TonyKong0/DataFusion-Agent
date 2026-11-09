import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.schema.models import SchemaMetadata
from app.schema.schema_graph import SchemaGraph
from app.schema.relationship import Relationship
from app.sql.join_path_planner import plan_join_path


SCHEMA = SchemaMetadata.model_validate_json((Path(__file__).parent / 'fixtures' / 'chinook_schema.json').read_text(encoding='utf-8'))
GRAPH = SchemaGraph(SCHEMA)
PAIRS = [
    ('customer', 'invoice'), ('invoice', 'invoiceline'), ('track', 'invoiceline'),
    ('genre', 'track'), ('genre', 'invoiceline'), ('artist', 'album'),
    ('artist', 'track'), ('artist', 'invoiceline'), ('mediatype', 'track'),
    ('mediatype', 'invoiceline'), ('playlist', 'playlisttrack'),
    ('playlist', 'track'), ('playlist', 'genre'), ('employee', 'customer'),
    ('employee', 'invoice'), ('customer', 'track'), ('customer', 'genre'),
    ('album', 'invoiceline'), ('invoice', 'genre'), ('employee', 'artist'),
]


@pytest.mark.parametrize('source,target', PAIRS)
def test_real_chinook_path(source, target):
    plan = plan_join_path([source, target], GRAPH)
    assert {source, target} <= set(plan['join_tables'])
    path = [Relationship(edge['left_table'], edge['left_column'], edge['right_table'],
                         edge['right_column'], edge['constraint_name']) for edge in plan['join_path']]
    assert GRAPH.validate_path(source, target, path)


def test_three_selected_tables_use_connected_edges():
    plan = plan_join_path(['genre', 'track', 'invoiceline'], GRAPH)
    assert plan['join_tables'] == ['genre', 'track', 'invoiceline']
    assert len(plan['join_path']) == 2


def test_unknown_table_is_rejected():
    with pytest.raises(AppError, match='选定表不在'):
        plan_join_path(['customer', 'invented'], GRAPH)

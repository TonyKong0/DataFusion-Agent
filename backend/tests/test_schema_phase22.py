from app.schema.models import ColumnMetadata, ForeignKeyMetadata, SchemaMetadata, TableMetadata
from app.schema.schema_graph import SchemaGraph
from app.schema.relationship import Relationship


def sample_graph():
    def table(name, key, fk=None):
        return TableMetadata(table_name=name, columns=[ColumnMetadata(
            name=key, type='int', primary_key=True, nullable=False), *(
            [ColumnMetadata(name=fk[1], type='int', primary_key=False, nullable=False)] if fk else [])],
            foreign_keys=[ForeignKeyMetadata(constraint_name='FK_'+name,
                column=fk[1], references_table=fk[0], references_column=fk[2])] if fk else [])
    return SchemaGraph(SchemaMetadata(database='chinook', tables=[
        table('Genre', 'GenreId'), table('Track', 'TrackId', ('Genre', 'GenreId', 'GenreId')),
        table('InvoiceLine', 'InvoiceLineId', ('Track', 'TrackId', 'TrackId')),
        table('Customer', 'CustomerId')] ))


def test_shortest_real_foreign_key_path():
    graph = sample_graph()
    path = graph.shortest_path('Genre', 'InvoiceLine')
    assert [(edge.from_table, edge.to_table) for edge in path] == [
        ('Genre', 'Track'), ('Track', 'InvoiceLine')]
    assert graph.validate_path('Genre', 'InvoiceLine', path)
    assert [edge.to_table for edge in graph.shortest_path('InvoiceLine', 'Genre')] == ['Track', 'Genre']


def test_neighbors_and_unconnected_tables():
    graph = sample_graph()
    assert graph.neighbors('Track') == ['Genre', 'InvoiceLine']
    assert graph.shortest_path('Genre', 'Genre') == []
    try:
        graph.shortest_path('Customer', 'Genre')
    except ValueError:
        pass
    else:
        assert False, 'Disconnected tables must not yield a path'


def test_invented_edge_is_rejected():
    graph = sample_graph()
    fake = Relationship('Genre', 'GenreId', 'Customer', 'CustomerId', 'fake')
    assert not graph.is_real_edge(fake)
    assert not graph.validate_path('Genre', 'Customer', [fake])

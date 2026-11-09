"""Typed representation of MySQL's actual table and column metadata."""

from pydantic import BaseModel


class ColumnMetadata(BaseModel):
    name: str
    type: str
    primary_key: bool
    nullable: bool
    comment: str | None = None


class ForeignKeyMetadata(BaseModel):
    constraint_name: str
    column: str
    references_table: str
    references_column: str


class TableMetadata(BaseModel):
    table_name: str
    columns: list[ColumnMetadata]
    foreign_keys: list[ForeignKeyMetadata]


class SchemaMetadata(BaseModel):
    database: str
    tables: list[TableMetadata]


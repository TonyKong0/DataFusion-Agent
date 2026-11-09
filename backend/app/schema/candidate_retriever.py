"""Deterministic candidate recall, restricted to the live schema."""

import re
from pathlib import Path

import yaml

from app.schema.models import SchemaMetadata


ALIASES_PATH = Path(__file__).resolve().parents[1] / 'config' / 'schema_aliases.yaml'


def _match(text: str, term: str) -> bool:
    if term.isascii() and term.isalnum():
        return bool(re.search(r'(?<![A-Za-z0-9])' + re.escape(term) + r'(?![A-Za-z0-9])', text, re.I))
    return term.casefold() in text.casefold()


def retrieve_candidates(question: str, elements: list[dict], metadata: SchemaMetadata,
                        table_k: int = 8, column_k: int = 20) -> dict:
    config = yaml.safe_load(ALIASES_PATH.read_text(encoding='utf-8'))
    actual_tables = {table.table_name.lower(): table for table in metadata.tables}
    actual_columns = {(table.table_name.lower(), col.name.lower()): col.name
                      for table in metadata.tables for col in table.columns}
    table_scores: dict[str, tuple[float, set[str]]] = {}
    column_scores: dict[tuple[str, str], tuple[float, set[str]]] = {}

    def table_hit(table: str, score: float, reason: str):
        key = table.lower()
        if key not in actual_tables:
            return
        old_score, reasons = table_scores.get(key, (0.0, set()))
        table_scores[key] = (min(1.0, max(old_score, score) + (0.03 if old_score else 0)), reasons | {reason})

    def column_hit(table: str, column: str, score: float, reason: str):
        key = (table.lower(), column.lower())
        if key not in actual_columns:
            return
        old_score, reasons = column_scores.get(key, (0.0, set()))
        column_scores[key] = (min(1.0, max(old_score, score) + (0.03 if old_score else 0)), reasons | {reason})
        table_hit(table, max(score - 0.13, 0.5), 'field:'+reason)

    for key, table in actual_tables.items():
        if _match(question, table.table_name):
            table_hit(key, 0.98, 'table_name')
        for alias in config.get('tables', {}).get(key, []):
            if _match(question, alias):
                table_hit(key, 0.93, 'table_alias:'+alias)
        for col in table.columns:
            if _match(question, col.name):
                column_hit(key, col.name, 0.95, 'column_name')

    for qualified, aliases in config.get('columns', {}).items():
        table, column = qualified.split('.', 1)
        for alias in aliases:
            if _match(question, alias):
                column_hit(table, column, 0.91, 'column_alias:'+alias)

    for keyword, qualified_names in config.get('business_keywords', {}).items():
        if keyword == '销售' and any(term in question for term in ('销售数量', '销售量')):
            continue
        if _match(question, keyword):
            for qualified in qualified_names:
                table, column = qualified.split('.', 1)
                column_hit(table, column, 0.79, 'business_keyword:'+keyword)

    for item in elements:
        if item.get('type') == 'entity':
            table_hit(str(item.get('canonical_value', '')), 0.96, 'semantic_entity')
        elif item.get('type') == 'filter' and item.get('name') == 'country':
            for table_name, column_name in (('customer', 'Country'), ('invoice', 'BillingCountry'),
                                            ('retail_transaction', 'Country')):
                column_hit(table_name, column_name, 0.82, 'semantic_filter:country')
        elif item.get('type') == 'sort' and item.get('name') == 'price':
            column_hit('track', 'UnitPrice', 0.87, 'semantic_sort:price')

    tables = [{'table': actual_tables[key].table_name, 'score': round(score, 3),
               'reasons': sorted(reasons)} for key, (score, reasons) in table_scores.items()]
    columns = [{'table': actual_tables[table].table_name,
                'column': actual_columns[(table, column)], 'score': round(score, 3),
                'reasons': sorted(reasons)} for (table, column), (score, reasons) in column_scores.items()]
    tables.sort(key=lambda item: (-item['score'], item['table']))
    columns.sort(key=lambda item: (-item['score'], item['table'], item['column']))
    return {'candidate_tables': tables[:table_k], 'candidate_columns': columns[:column_k]}

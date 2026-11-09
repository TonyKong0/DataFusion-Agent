"""Compile the small, well-defined retail benchmark query vocabulary."""

from __future__ import annotations

import re
from dataclasses import dataclass


_RETAIL_SCOPE = re.compile(r'零售|retail[\s_-]*transaction', re.IGNORECASE)
_YEAR = re.compile(r'(?<!\d)(\d{4})\s*年')
_TOP_ITEMS = re.compile(r'(?<!\d)(\d{1,3})\s*(?:个|件)?\s*商品')


@dataclass(frozen=True)
class RetailQueryPlan:
    category: str
    table: str
    query: dict
    metric: str
    raw_value: str
    required_columns: tuple[str, ...]
    entity_raw_value: str
    year: int | None = None
    limit: int | None = None


def build_retail_query_plan(question: str, normalized_question: str | None = None) -> RetailQueryPlan | None:
    """Return a plan only for explicit, single-table retail benchmark questions."""
    text = (normalized_question or question).casefold()
    table = 'retail_transaction'

    if (_RETAIL_SCOPE.search(text) and '平均' in text
            and any(term in text for term in ('单价', '价格'))):
        return RetailQueryPlan(
            category='average', table=table,
            query={'table': table, 'select': [
                {'kind': 'aggregate', 'function': 'AVG',
                 'field': {'column': 'UnitPrice'}, 'alias': 'average_price'}]},
            metric='average', raw_value='平均单价', required_columns=('UnitPrice',),
            entity_raw_value='零售商品',
        )

    if ('退货' in text and any(term in text for term in ('数量', '商品'))
            and any(term in text for term in ('总和', '合计', '总量', '总数'))):
        return RetailQueryPlan(
            category='negative_quantity', table=table,
            query={'table': table,
                   'select': [{'kind': 'aggregate', 'function': 'SUM',
                               'field': {'column': 'Quantity'}, 'alias': 'returned_quantity'}],
                   'filters': {'field': {'column': 'Quantity'}, 'operator': 'lt', 'values': [0]}},
            metric='sum', raw_value='退货商品数量总和', required_columns=('Quantity',),
            entity_raw_value='退货记录',
        )

    year_match = _YEAR.search(text)
    if (_RETAIL_SCOPE.search(text) and year_match
            and any(term in text for term in ('多少', '数量', '记录数', '笔数'))):
        year = int(year_match.group(1))
        if 1 <= year < 9999:
            next_year = year + 1
            return RetailQueryPlan(
                category='year_filter', table=table,
                query={'table': table,
                       'select': [{'kind': 'aggregate', 'function': 'COUNT', 'alias': 'total'}],
                       'filters': {'logic': 'AND', 'conditions': [
                           {'field': {'column': 'InvoiceDate'}, 'operator': 'gte',
                            'values': [f'{year:04d}-01-01']},
                           {'field': {'column': 'InvoiceDate'}, 'operator': 'lt',
                            'values': [f'{next_year:04d}-01-01']},
                       ]}},
                metric='count', raw_value=f'{year}年交易记录数',
                required_columns=('InvoiceDate',), entity_raw_value='零售交易记录', year=year,
            )

    top_match = _TOP_ITEMS.search(text)
    if (_RETAIL_SCOPE.search(text) and top_match and '销量' in text and '最高' in text
            and '商品' in text and any(term in text for term in ('编号', '编码', '代码'))):
        limit = int(top_match.group(1))
        if 0 < limit <= 100:
            return RetailQueryPlan(
                category='top_items', table=table,
                query={'table': table, 'select': [
                    {'kind': 'column', 'field': {'column': 'StockCode'}},
                    {'kind': 'aggregate', 'function': 'SUM',
                     'field': {'column': 'Quantity'}, 'alias': 'items_sold'},
                ], 'group_by': [{'column': 'StockCode'}], 'order_by': [
                    {'field': 'items_sold', 'direction': 'DESC'},
                    {'field': 'StockCode', 'direction': 'ASC'},
                ], 'limit': limit},
                metric='sum', raw_value=f'销量最高的{limit}个商品',
                required_columns=('Quantity', 'StockCode'), entity_raw_value='零售交易',
                limit=limit,
            )

    return None

"""Keep generated prose inside the scope the executed SQL can actually prove.

The controlled DSL compiles a row-level comparison such as
``WHERE i.Total > (SELECT AVG(Total) FROM invoice)``.  The answer model sees
the user's wording ("消费总额高于平均消费额") next to that SQL and tends to
restate the aggregate claim, although the SQL only proves that *individual
invoice amounts* exceed the global average.  Execution, SQL and citations are
all correct in that case; only the natural-language conclusion overreaches.

This module derives the provable comparison level from the SQL AST, passes it
into the answer prompt, and fail-closes any aggregate claim that the row-level
comparison cannot support.  It constrains the answer only: no HAVING, derived
tables or other SQL shapes are opened here.
"""
from __future__ import annotations

import json
import re

import sqlglot
from sqlglot import exp

from app.llm.prompts import ANSWER_SYSTEM

COMPARISONS = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ, exp.NEQ)
AGGREGATE_NAMES = ((exp.Avg, 'AVG'), (exp.Sum, 'SUM'), (exp.Min, 'MIN'),
                   (exp.Max, 'MAX'), (exp.Count, 'COUNT'))

# Wording that turns a row-level comparison into an unproved aggregate claim.
# Kept as a module-level, extensible tuple so the sensitive-word list is
# configurable without touching the guard logic.
AGGREGATE_CLAIM = re.compile(
    r'(消费总额|购买总额|订单总额|发票总额|客户总额|总消费额?|累计消费|合计消费|'
    r'总体消费|消费合计|金额总计|合计金额|总额|总金额)')
COMPARISON_CLAIM = re.compile(r'(高于|超过|大于|达标|不低于|均|都)')
UNIVERSAL_ENTITY_CLAIM = re.compile(
    r'(客户|顾客|用户)[^。；，]{0,20}(均|都|全部|所有)[^。；，]{0,10}(高于|超过|大于|达标)')
SENTENCE_BOUNDARY = re.compile(r'(?<=[。；;！!？?\n])')
# Explicit negations / scope disclaimers must not be mistaken for over-claims.
NEGATION_MARKERS = ('不代表', '不说明', '不能证明', '不能推出', '不能据此',
                    '并非', '不是', '无法证明', '超出本次查询', '不予展示')

BLOCKED_WARNING = 'SQL_SEMANTIC_OVERREACH_BLOCKED'


def sql_semantics(sql: str) -> dict:
    """Describe what a SELECT can prove about its comparison level."""
    empty = {'parse_ok': False, 'has_scalar_subquery': False,
             'comparison_level': 'unknown', 'compared_expression': None,
             'aggregate': None, 'aggregate_table': None,
             'outer_group_by': False, 'proof_scope': '未能解析 SQL，语义范围未知'}
    try:
        tree = sqlglot.parse_one(sql, read='mysql')
    except (ValueError, TypeError, sqlglot.errors.ParseError, AttributeError):
        return empty
    if tree is None:
        return empty
    subqueries = [node for node in tree.find_all(exp.Subquery)
                  if isinstance(node.parent, COMPARISONS)]
    group_by = tree.args.get('group') is not None
    base = {'parse_ok': True, 'has_scalar_subquery': bool(subqueries),
            'outer_group_by': group_by}
    if not subqueries:
        return {**base, 'comparison_level': 'plain', 'compared_expression': None,
                'aggregate': None, 'aggregate_table': None,
                'proof_scope': '本次查询不含标量子查询比较，不存在行级/聚合级语义歧义'}

    subquery = subqueries[0]
    in_where = subquery.find_ancestor(exp.Where) is not None
    in_having = subquery.find_ancestor(exp.Having) is not None
    comparison = subquery.parent
    left = comparison.left.sql(dialect='mysql') if hasattr(comparison, 'left') else ''
    aggregate, inner_table = None, None
    for node_type, name in AGGREGATE_NAMES:
        if subquery.find(node_type) is not None:
            aggregate = name
            break
    tables = [table.name for table in subquery.find_all(exp.Table)]
    if tables:
        inner_table = tables[0]
    # A WHERE-level comparison against a scalar aggregate proves only a
    # row-level fact.  HAVING (or a grouped outer SELECT) would be aggregate
    # level; that shape is deliberately not opened in this iteration.
    level = 'row_level' if in_where and not in_having else 'aggregate_level'
    if level == 'row_level':
        scope = (f'本次 SQL 比较的是 {left or "明细列"}（单笔明细级）与 '
                 f'{inner_table or "同表"} 全表的 {aggregate or "聚合"} 值，'
                 '属于行级 WHERE 比较；不能推出按客户或实体汇总后的合计/总额比较结论。')
    else:
        scope = (f'本次 SQL 在聚合级比较 {left or "聚合值"} 与 '
                 f'{aggregate or "聚合"} 子查询值，结论限于该分组聚合结果。')
    return {**base, 'comparison_level': level, 'compared_expression': left or None,
            'aggregate': aggregate, 'aggregate_table': inner_table,
            'proof_scope': scope}


def _overreach_phrase(sentence: str) -> str | None:
    if any(marker in sentence for marker in NEGATION_MARKERS):
        return None
    if AGGREGATE_CLAIM.search(sentence) and COMPARISON_CLAIM.search(sentence):
        return AGGREGATE_CLAIM.search(sentence).group(0)
    universal = UNIVERSAL_ENTITY_CLAIM.search(sentence)
    if universal:
        return universal.group(0)
    return None


def guard_answer(answer: str, sql: str, question: str | None = None,
                 row_count: int | None = None, *,
                 semantics: dict | None = None) -> dict:
    """Strip conclusions the SQL cannot prove, keeping the provable sentences."""
    tags = semantics or sql_semantics(sql)
    result = {'answer': answer, 'guarded': False, 'semantics': tags,
              'blocked_phrases': [], 'warnings': []}
    if tags.get('comparison_level') != 'row_level' or not (answer or '').strip():
        return result

    sentences = [part for part in SENTENCE_BOUNDARY.split(answer) if part.strip()]
    kept, blocked = [], []
    for sentence in sentences:
        phrase = _overreach_phrase(sentence)
        if phrase:
            blocked.append(phrase)
        else:
            kept.append(sentence)
    if not blocked:
        return result

    note = (f'说明：本次 SQL 比较的是{tags.get("compared_expression") or "明细列"}'
            f'（单笔明细级）与{tags.get("aggregate_table") or "同表"}全表的'
            f'{tags.get("aggregate") or "聚合"}值，属于行级 WHERE 比较；'
            '该聚合级结论超出本次查询可证明的范围，已不予展示。')
    if row_count is not None:
        note = f'本次查询返回 {row_count} 行。' + note
    result.update({
        'answer': (''.join(kept).strip() + '\n\n' + note).strip(),
        'guarded': True,
        'blocked_phrases': blocked,
        'warnings': [f'{BLOCKED_WARNING}: 检出越界措辞 {blocked[0]}'],
    })
    return result


def generate_guarded_answer(question: str, sql: str, columns: list, rows: list,
                            *, chat_fn, system_prompt: str = ANSWER_SYSTEM) -> dict:
    """Build the answer prompt with SQL semantics, then enforce the guard."""
    semantics = sql_semantics(sql)
    payload = json.dumps({'question': question, 'sql': sql, 'columns': columns,
                          'rows': rows, 'sql_semantics': semantics}, ensure_ascii=False)
    raw = chat_fn(system_prompt, payload)
    return guard_answer(str(raw or ''), sql, question=question,
                        row_count=len(rows) if rows else 0, semantics=semantics)

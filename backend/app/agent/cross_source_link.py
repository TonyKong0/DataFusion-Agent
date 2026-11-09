"""Verify that a dependent tool used the prior source before claiming a cross-source link."""
from decimal import Decimal, InvalidOperation
import sqlglot
from sqlglot import exp
from app.agent.result_values import _extract_number, _primary_value, _source_contains_number


def _where_uses_number(sql: str, number: int | float) -> bool:
    try:
        expression = sqlglot.parse_one(sql, read='mysql')
        expected = Decimal(str(number))
        return any(Decimal(literal.this) == expected
                   for where in expression.find_all(exp.Where)
                   for comparison in where.find_all((exp.GT, exp.GTE, exp.LT, exp.LTE))
                   for literal in comparison.find_all(exp.Literal)
                   if literal.is_number)
    except (ValueError, TypeError, InvalidOperation, sqlglot.errors.ParseError):
        return False


def build_cross_source_link(plan, step_results: dict, evidence: list[dict]) -> dict:
    if plan.route != 'CROSS_SOURCE':
        return {'status': 'single_source'}
    dependent = next((step for step in plan.steps if step.inputs_from), None)
    if dependent is None:
        return {'status': 'parallel', 'summary': '本次分别查询两个来源，没有把一边的结果作为另一边的查询条件。'}
    target_result = step_results.get(dependent.id)
    key, reference = next(iter(dependent.inputs_from.items()))
    source_id = reference.partition('.data.')[0]
    source_result = step_results.get(source_id)
    source_evidence = [item for item in evidence if item['step_id'] == source_id]
    target_evidence = [item for item in evidence if item['step_id'] == dependent.id]
    unverified = {'status': 'unverified', 'source_step': source_id, 'target_step': dependent.id,
                  'summary': '两步查询未形成可核验的关联，不能据此给出跨源结论。'}
    if not source_result or not source_result.success or not target_result or not target_result.success:
        return unverified
    if key == 'threshold' and source_result.tool == 'document_search' and target_result.tool == 'database_query':
        value = _extract_number(source_result.data)
        if value is None:
            return unverified
        document = next((item for item in source_evidence if item['source_type'] == 'document'
                         and _source_contains_number(str(item['content']), value)), None)
        database = next((item for item in target_evidence if item['source_type'] == 'database'
                         and _where_uses_number(item['provenance']['sql'], value)), None)
        if not document or not database:
            return unverified
        db_value = _primary_value(target_result.data)
        result_text = f'数据库查询结果为 {db_value}' if db_value is not None else '数据库查询已完成'
        return {'status': 'linked', 'binding': {'name': key, 'value': value},
                'source_step': source_id, 'target_step': dependent.id,
                'evidence_ids': [document['evidence_id'], database['evidence_id']],
                'summary': f'已将文档第 {document["provenance"]["page"]} 页的数值 {value} 用作 SQL 查询条件；{result_text}。'}
    if key == 'topic' and source_result.tool == 'database_query' and target_result.tool == 'document_search':
        value = _primary_value(source_result.data)
        if not isinstance(value, str) or len(value.strip()) < 2:
            return unverified
        topic = value.strip()
        database = next((item for item in source_evidence if item['source_type'] == 'database'), None)
        document = next((item for item in target_evidence if item['source_type'] == 'document'
                         and topic.casefold() in str(item['content']).casefold()), None)
        if not database or not document:
            return unverified
        return {'status': 'linked', 'binding': {'name': key, 'value': topic},
                'source_step': source_id, 'target_step': dependent.id,
                'evidence_ids': [database['evidence_id'], document['evidence_id']],
                'summary': f'数据库查得“{topic}”，并在文档第 {document["provenance"]["page"]} 页找到包含该名称的原文。'}
    return unverified

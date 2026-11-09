import re
from decimal import Decimal, InvalidOperation
from app.agent.citation_guard import guard_claims


COUNT_SUBJECTS = (
    (('客户', '顾客'), '位客户'),
    (('艺术家', '歌手'), '位艺术家'),
    (('音乐类型', '流派', '曲风'), '种音乐类型'),
    (('专辑',), '张专辑'),
    (('歌曲', '曲目'), '首歌曲'),
    (('员工',), '位员工'),
    (('发票',), '张发票'),
    (('订单',), '笔订单'),
    (('付款',), '笔付款'),
)
COLUMN_LABELS = {
    'customer_count': '客户数', 'artist_count': '艺术家数', 'genre_count': '音乐类型数',
    'album_count': '专辑数', 'track_count': '曲目数', 'employee_count': '员工数',
    'invoice_count': '发票数', 'count': '记录数', 'count(*)': '记录数',
    'customerid': '客户编号', 'customer_id': '客户编号', 'firstname': '名字',
    'lastname': '姓氏', 'email': '邮箱', 'invoicedate': '发票日期',
    'total': '金额', 'unitprice': '单价', 'quantity': '数量', 'name': '名称',
    'title': '标题', 'genre': '音乐类型', 'artist': '艺术家',
}


def _numbers(text: str) -> set[Decimal]:
    text = re.sub(r'(?<=\d)[,，](?=\d{3}(?:\D|$))', '', text)
    values = set()
    for value in re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', text):
        try:
            values.add(Decimal(value))
        except InvalidOperation:
            continue
    return values


def _numbers_supported(answer: str, sources: list[dict], data: dict) -> bool:
    # File names, page references and list numbering are metadata, not factual claims.
    from app.services.document_facts import _display_title
    factual = re.sub(r'(?m)^\s*\d+\s*[.、．)]\s*', '', answer)
    filenames = [item.get('source_name', '') for item in sources]
    filenames.extend(item.get('filename', '') for item in data.get('document_names', []))
    names = set()
    for filename in filenames:
        if filename:
            names.update((filename, filename.rsplit('.', 1)[0], _display_title({'filename': filename})))
    for name in sorted(names, key=len, reverse=True):
        factual = factual.replace(name, '')
    pages = {str(item.get('provenance', {}).get('page')) for item in sources}
    factual = re.sub(r'第\s*(\d+)\s*页',
                     lambda match: '' if match.group(1) in pages else match.group(0), factual)
    original = '\n'.join(str(item['content']) for item in sources)
    return _numbers(factual) <= _numbers(original)


def _row_values(columns: list, row) -> dict:
    if isinstance(row, dict):
        return row
    if isinstance(row, (list, tuple)):
        return dict(zip(columns, row))
    return {}


def _column_label(column) -> str:
    name = str(column)
    return COLUMN_LABELS.get(name.casefold(), name.replace('_', ' ').strip())


def _count_unit(question: str, column: str) -> str | None:
    normalized = question.casefold()
    column_name = column.casefold()
    for words, unit in COUNT_SUBJECTS:
        if any(word.casefold() in normalized or word.casefold() in column_name for word in words):
            return unit
    return None


def _database_result_text(content: dict, question: str, sql: str) -> str:
    columns = content.get('columns') or []
    rows = content.get('rows') or []
    if not rows:
        return '数据库中没有符合条件的记录。'

    row_count = content.get('row_count', len(rows))
    mapped = [_row_values(columns, row) for row in rows[:5]]
    is_count = bool(re.search(r'\bCOUNT\s*\(', sql, re.IGNORECASE))
    if len(mapped) == 1 and len(mapped[0]) == 1:
        column, value = next(iter(mapped[0].items()))
        if is_count:
            unit = _count_unit(question, str(column))
            if unit:
                return f'数据库中共有 {value}{unit}。'
            return f'数据库查询结果：共 {value} 条记录。'
        return f'数据库查询结果：{_column_label(column)}为 {value}。'

    def format_row(row: dict) -> str:
        return '；'.join(f'{_column_label(column)}：{value if value is not None else "—"}'
                         for column, value in row.items())

    if len(mapped) == 1:
        return f'数据库查询结果：{format_row(mapped[0])}。'
    details = '\n'.join(f'- {format_row(row)}' for row in mapped)
    return f'数据库查询返回 {row_count} 行，以下是前 {len(mapped)} 行：\n{details}'


def compose_answer(evidence: list[dict], fusion: dict, tool_results: dict | None = None,
                   cross_source_link: dict | None = None) -> dict:
    claims = []
    if cross_source_link and cross_source_link.get('status') == 'linked':
        claims.append({'text': cross_source_link['summary'], 'evidence_ids': cross_source_link['evidence_ids']})
    summarized_document_steps = set()
    rejected_document_answers = []
    for step_id, result in (tool_results or {}).items():
        if result.tool != 'document_search' or not result.success:
            continue
        sources = [item for item in evidence if item['step_id'] == step_id and item['source_type'] == 'document']
        answer = str(result.data.get('answer') or '').strip()
        if sources and answer and _numbers_supported(answer, sources, result.data):
            claims.append({'text': answer, 'evidence_ids': [item['evidence_id'] for item in sources]})
            summarized_document_steps.add(step_id)
        elif sources:
            # Do not silently replace an unverified answer with large raw chunks.
            summarized_document_steps.add(step_id)
            rejected_document_answers.append('材料回答包含未获原文支持的数字，已停止展示该结论')
    for item in evidence:
        kind, content = item['source_type'], item['content']
        source_id = item['evidence_id']
        if kind == 'database':
            result = (tool_results or {}).get(item['step_id'])
            data = result.data if result and result.tool == 'database_query' else {}
            text = _database_result_text(content, str(data.get('question') or ''),
                                         str(item.get('provenance', {}).get('sql') or ''))
        elif kind == 'document':
            if item['step_id'] in summarized_document_steps:
                continue
            page = item['provenance']['page']
            text = f'文档第 {page} 页原文：{str(content).strip()[:500]}'
        elif kind == 'formula':
            text = f'文档第 {item["provenance"]["page"]} 页公式计算结果：{content}'
        else:
            continue
        ids = [source_id]
        if kind == 'formula' and item['provenance'].get('parameter_source') == 'database':
            ids.extend(source['evidence_id'] for source in evidence if source['source_type'] == 'database')
        claims.append({'text': text, 'evidence_ids': ids})
    accepted, warnings = guard_claims(claims, evidence)
    warnings.extend(rejected_document_answers)
    for result in (tool_results or {}).values():
        warnings.extend(result.data.get('warnings') or [])
    for conflict in fusion.get('conflicts', []):
        ids = conflict['evidence_ids']
        if all(any(item['evidence_id'] == identifier for item in evidence) for identifier in ids):
            accepted.append({'text': f'{conflict["topic"]}在不同来源中的值不一致：{conflict["values"]}，暂不能判定哪一个正确。',
                             'evidence_ids': ids})
            warnings.append(f'{conflict["topic"]}存在来源冲突')
    if fusion.get('missing'):
        warnings.extend(fusion['missing'])
    # Evidence identifiers remain available on structured claims and in the
    # evidence panel; they are internal keys, not part of the user-facing prose.
    answer = '\n\n'.join(claim['text'] for claim in accepted)
    if not answer:
        failure = next((result for result in (tool_results or {}).values()
                        if not result.success and result.error), None)
        if failure and failure.error.get('code') in {'LLM_REQUEST_FAILED', 'LLM_INVALID_RESPONSE'}:
            answer = ('模型调用失败，本次问答未完成。请稍后重试或检查模型服务连接；'
                      '这次失败不能说明材料中没有答案。')
        elif failure:
            answer = '本次查询未完成：' + str(failure.error.get('message') or '工具执行失败')
        elif rejected_document_answers:
            answer = '材料回答中的数字未通过来源核对，暂不展示该结论。请查看引用原文。'
        else:
            answer = '当前证据不足，无法确认答案。'
    sql = [item['provenance']['sql'] for item in evidence if item['source_type'] == 'database']
    return {'answer': answer, 'claims': accepted, 'sources': evidence, 'sql': sql,
            'warnings': warnings, 'conflicts': fusion.get('conflicts', [])}

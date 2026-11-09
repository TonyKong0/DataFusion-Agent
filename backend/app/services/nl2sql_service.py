import json
import re
import time
from app.core.errors import AppError
from app.core.config import get_settings
from app.db.schema_loader import load_schema
from app.llm.deepseek_client import chat, chat_json
from app.llm.prompts import NL2SQL_SYSTEM, ANSWER_SYSTEM
from app.services.sql_validator import validate_sql
from app.services.sql_executor import execute_sql
from app.sql.query_dsl import compile_query_dsl, render_pymysql_sql
from app.services.retail_query import build_retail_query_plan
from app.services.answer_semantic_guard import generate_guarded_answer
from app.semantic.normalizer import normalize_question
from app.semantic.element_extractor import extract_elements
from app.semantic.semantic_validator import validate_semantics
from app.semantic.clarification_manager import create_clarification

ENTITY_LABELS = {
    'artist': ('艺术家', '位'), 'genre': ('音乐类型', '种'),
    'customer': ('客户', '位'), 'employee': ('员工', '位'),
    'album': ('专辑', '张'), 'track': ('歌曲', '首'),
    'invoice': ('订单', '笔'), 'retail_transaction': ('零售交易记录', '条'),
}


def _format_simple_answer(question: str, sql: str, table: str,
                          columns: list[str], rows: list[list]) -> str | None:
    """Format facts directly when the SQL result needs no interpretation."""
    if not rows:
        return '未查到符合条件的数据。'
    label, unit = ENTITY_LABELS.get(table.lower(), ('记录', '条'))
    if (len(rows) == 1 and len(columns) == 1 and len(rows[0]) == 1
            and isinstance(rows[0][0], (int, float)) and not isinstance(rows[0][0], bool)
            and re.search(r'\bCOUNT\s*\(', sql, re.IGNORECASE)):
        qualifier = '符合条件的' if re.search(r'\bWHERE\b', sql, re.IGNORECASE) else ''
        return f'{qualifier}{label}共有 {rows[0][0]} {unit}。'
    if table.lower() == 'retail_transaction':
        if (len(rows) == 1 and len(columns) == 1 and len(rows[0]) == 1
                and isinstance(rows[0][0], (int, float)) and not isinstance(rows[0][0], bool)):
            if columns[0].lower() == 'average_price':
                return f'零售商品的平均单价是 {rows[0][0]:g}。'
            if columns[0].lower() == 'returned_quantity':
                return f'退货记录中的商品数量总和是 {rows[0][0]:g}。'
        if (len(columns) == 2 and columns[0].lower() == 'stockcode'
                and columns[1].lower() == 'items_sold'
                and all(len(row) == 2 for row in rows)):
            entries = '、'.join(f'{row[0]}（{row[1]:g}）' for row in rows)
            return f'销量最高的 {len(rows)} 个商品编号及购买数量为：{entries}。'
    display_index = None
    if len(columns) == 1 and columns[0].lower() in {'name', 'title'}:
        display_index = 0
    elif (len(columns) == 2 and table.lower() in {'genre', 'artist'}
          and not re.search(r'编号|\bID\b|标识', question, re.IGNORECASE)):
        lowered = [column.lower() for column in columns]
        if 'name' in lowered and f'{table.lower()}id' in lowered:
            display_index = lowered.index('name')
    if (display_index is not None and all(len(row) == len(columns)
                                           and isinstance(row[display_index], str) for row in rows)):
        names = '、'.join(row[display_index] for row in rows)
        return f'当前查询返回 {len(rows)} {unit}{label}：{names}。'
    return None


def _artist_roster_request(question: str, extracted: dict) -> tuple[bool, bool]:
    """Return whether an artist roster is requested and whether 'all' is explicit."""
    elements = extracted['elements']
    entities = {item.canonical_value for item in elements if item.type == 'entity'}
    if entities != {'Artist'} or any(item.type in {'filter', 'time', 'sort', 'limit'} for item in elements):
        return False, False
    has_count = any(item.type == 'metric' and item.canonical_value == 'count' for item in elements)
    wants_names = bool(re.search(r'分别|都是谁|有哪些|名单|名字|姓名|列出|列举|展示', question))
    explicit_all = bool(re.search(r'全部|所有|每一位|完整', question))
    return wants_names and (has_count or explicit_all), explicit_all


def _track_superlative(question: str, extracted: dict) -> str | None:
    elements = extracted['elements']
    entities = {item.canonical_value for item in elements if item.type == 'entity'}
    if entities != {'Track'} or any(item.type in {'filter', 'time', 'limit'} for item in elements):
        return None
    if re.search(r'最长|时长最长|播放时间最长', question):
        return 'longest'
    if '最近' not in question and re.search(r'最流行|最受欢迎|最热门', question):
        return 'popular'
    return None


def query(question: str, confirmed: bool = False, clarification_completed: bool = False,
          original_question: str | None = None) -> dict:
    from app.services.multitable_service import query as multitable_query
    from app.services.multitable_service import is_multitable_intent
    if is_multitable_intent(question):
        return multitable_query(question, confirmed=confirmed,
                                clarification_completed=clarification_completed,
                                original_question=original_question)
    start = time.perf_counter()
    trace = []
    diagnostic = {'stage': None, 'sql': None, 'table': None, 'query': None}

    def attach_error_context(error: Exception, stage: str | None = None) -> None:
        context = {
            'trace': list(trace),
            'failed_step': stage or diagnostic['stage'],
            'generated_sql': diagnostic['sql'],
            'generated_query': diagnostic['query'],
            'selected_table': diagnostic['table'],
        }
        for name, value in context.items():
            try:
                setattr(error, name, value)
            except (AttributeError, TypeError):
                pass

    def step(name: str, action):
        before = time.perf_counter()
        diagnostic['stage'] = name
        try:
            result = action()
        except Exception as error:
            trace.append({'id': f'step_{len(trace)+1:02}', 'type': 'tool', 'name': name,
                          'step': name, 'status': 'failed', 'duration_ms': round((time.perf_counter()-before)*1000),
                          'error_type': type(error).__name__,
                          'error_code': getattr(error, 'code', type(error).__name__)})
            attach_error_context(error, name)
            raise
        trace.append({'id': f'step_{len(trace)+1:02}', 'type': 'tool', 'name': name,
                      'step': name, 'status': 'success', 'duration_ms': round((time.perf_counter()-before)*1000)})
        return result

    try:
        normalized = step('question_normalize', lambda: normalize_question(question))

        retail_plan = build_retail_query_plan(question, normalized['normalized_question'])
        schema = None
        if retail_plan:
            schema = step('schema_load', load_schema)
            retail_table = next((item for item in schema
                                 if item['table'].lower() == retail_plan.table.lower()), None)
            available_columns = ({column['name'].lower() for column in retail_table['columns']}
                                 if retail_table else set())
            required_columns = {column.lower() for column in retail_plan.required_columns}
            if retail_table and required_columns <= available_columns:
                diagnostic['query'] = retail_plan.query
                diagnostic['table'] = retail_plan.table
                compiled = step('query_compile', lambda: compile_query_dsl(
                    retail_plan.query, schema, max_rows=get_settings().max_sql_rows))
                diagnostic['sql'] = compiled.sql
                diagnostic['table'] = compiled.table
                sql, table = step('sql_validate', lambda: validate_sql(
                    compiled.sql, compiled.table, schema))
                executable_sql = render_pymysql_sql(sql)
                diagnostic['sql'] = sql
                diagnostic['table'] = table
                if compiled.params:
                    columns, rows = step('sql_execute', lambda: execute_sql(executable_sql, compiled.params))
                else:
                    columns, rows = step('sql_execute', lambda: execute_sql(executable_sql))
                elements = [
                    {'type': 'entity', 'canonical_value': 'RetailTransaction', 'source': 'rule',
                     'confidence': 1.0, 'name': None, 'raw_value': retail_plan.entity_raw_value},
                    {'type': 'metric', 'canonical_value': retail_plan.metric, 'source': 'rule',
                     'confidence': 1.0, 'name': None, 'raw_value': retail_plan.raw_value},
                ]
                if retail_plan.year is not None:
                    elements.append({'type': 'time', 'canonical_value': str(retail_plan.year),
                                     'source': 'rule', 'confidence': 1.0, 'name': 'year',
                                     'raw_value': f'{retail_plan.year}年'})
                if retail_plan.limit is not None:
                    elements.append({'type': 'limit', 'canonical_value': retail_plan.limit,
                                     'source': 'rule', 'confidence': 1.0, 'name': None,
                                     'raw_value': str(retail_plan.limit)})
                semantic = {
                    'original_question': original_question or question,
                    'normalized_question': normalized['normalized_question'],
                    'changes': normalized['changes'], 'elements': elements,
                    'fallback_used': False,
                    'validation': {'valid': True, 'need_clarification': False,
                                   'missing': [], 'ambiguities': [], 'unsupported': [],
                                   'low_confidence': False, 'conflicts': [], 'error': None},
                    'canonical_question': normalized['normalized_question'],
                }
                def generate_answer():
                    simple = _format_simple_answer(question, sql, table, columns, rows)
                    if simple:
                        return simple, {'guarded': False}
                    guarded = generate_guarded_answer(question, sql, columns, rows, chat_fn=chat)
                    return guarded['answer'], guarded
                answer, answer_guard = step('answer_generate', generate_answer)
                return {'success': True, 'question': question, 'answer': answer,
                        'answer_guard': answer_guard,
                        'need_clarification': False, 'sql': sql, 'table': table,
                        'columns': columns, 'rows': rows, 'row_count': len(rows),
                        'sources': [], 'semantic': semantic, 'trace': trace,
                        'latency_ms': round((time.perf_counter()-start)*1000)}

        extracted = step('elements_extract', lambda: extract_elements(question, normalized['normalized_question']))
        validation = step('semantic_validate', lambda: validate_semantics(question, extracted, confirmed=confirmed))
        semantic = {'original_question': original_question or question,
                    'normalized_question': normalized['normalized_question'],
                    'changes': normalized['changes'], 'elements': [item.to_dict() for item in extracted['elements']],
                    'fallback_used': extracted['fallback_used'], 'validation': validation,
                    'canonical_question': normalized['normalized_question'] if validation['valid'] else None}
        if validation['need_clarification']:
            clarification = create_clarification(question, validation, original_question=original_question)
            return {'success': True, 'question': question, 'need_clarification': True,
                    'answer': clarification['question'], 'clarification': clarification,
                    'sql': None, 'table': None, 'columns': [], 'rows': [], 'row_count': 0,
                    'sources': [], 'semantic': semantic, 'trace': trace,
                    'latency_ms': round((time.perf_counter()-start)*1000)}
        step('clarification_completed' if clarification_completed else 'clarification_skipped', lambda: True)
        canonical_question = step('canonical_question_build', lambda: normalized['normalized_question'])
        superlative = _track_superlative(canonical_question, extracted)
        if superlative:
            schema = step('schema_load', load_schema)
            track = next((item for item in schema if item['table'].lower() == 'track'), None)
            track_columns = {column['name'].lower() for column in track['columns']} if track else set()
            if superlative == 'longest' and {'trackid', 'name', 'milliseconds'} <= track_columns:
                sql, table = step('sql_validate', lambda: validate_sql(
                    'SELECT TrackId, Name, Milliseconds FROM track '
                    'ORDER BY Milliseconds DESC, TrackId ASC LIMIT 1', track['table'], schema))
                columns, rows = step('sql_execute', lambda: execute_sql(sql))
                if rows:
                    duration_ms = int(rows[0][2])
                    hours, remainder = divmod(duration_ms // 1000, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    answer = (f'最长的歌曲是《{rows[0][1]}》，时长约 {hours} 小时 '
                              f'{minutes} 分 {seconds} 秒（{duration_ms:,} 毫秒）。')
                else:
                    answer = '数据库中没有歌曲记录。'
                return {'success': True, 'question': question, 'answer': answer,
                        'need_clarification': False, 'sql': sql, 'table': table,
                        'columns': columns, 'rows': rows, 'row_count': len(rows),
                        'sources': [], 'semantic': semantic, 'trace': trace,
                        'latency_ms': round((time.perf_counter()-start)*1000)}
            sales_table = next((item for item in schema if item['table'].lower() == 'invoiceline'), None)
            sales_columns = {column['name'].lower() for column in sales_table['columns']} if sales_table else set()
            if (superlative == 'popular' and {'trackid', 'name'} <= track_columns
                    and {'trackid', 'quantity'} <= sales_columns):
                sales_sql, _ = step('sql_sales_validate', lambda: validate_sql(
                    'SELECT TrackId, SUM(Quantity) AS sold FROM invoiceline '
                    'GROUP BY TrackId ORDER BY sold DESC, TrackId ASC LIMIT 1',
                    sales_table['table'], schema))
                _, sales_rows = step('sql_sales_execute', lambda: execute_sql(sales_sql))
                if sales_rows:
                    track_id, sold = int(sales_rows[0][0]), sales_rows[0][1]
                    lookup_sql, _ = step('sql_track_validate', lambda: validate_sql(
                        f'SELECT TrackId, Name FROM track WHERE TrackId = {track_id} LIMIT 1',
                        track['table'], schema))
                    _, track_rows = step('sql_track_execute', lambda: execute_sql(lookup_sql))
                    if not track_rows:
                        raise AppError('SQL_EXECUTION_FAILED', '销量记录对应的歌曲不存在', 502)
                    rows = [[track_id, track_rows[0][1], sold]]
                    answer = (f'按 Chinook 数据库的购买数量衡量，销量最高的歌曲之一是《{track_rows[0][1]}》，'
                              f'售出 {sold:g} 份。数据库没有播放量数据，因此这里的“流行”指销量。')
                else:
                    lookup_sql, rows = None, []
                    answer = '数据库中没有歌曲购买记录，无法按销量判断最流行的歌曲。'
                return {'success': True, 'question': question, 'answer': answer,
                        'need_clarification': False, 'sql': sales_sql, 'lookup_sql': lookup_sql,
                        'table': sales_table['table'], 'columns': ['TrackId', 'Name', 'sold'],
                        'rows': rows, 'row_count': len(rows), 'sources': [],
                        'semantic': semantic, 'trace': trace,
                        'latency_ms': round((time.perf_counter()-start)*1000)}
        roster_requested, explicit_all = _artist_roster_request(canonical_question, extracted)
        if roster_requested:
            schema = step('schema_load', load_schema)
            artist = next((table for table in schema if table['table'].lower() == 'artist'), None)
            if artist and {'artistid', 'name'}.issubset({column['name'].lower() for column in artist['columns']}):
                count_sql, table = step('sql_count_validate', lambda: validate_sql(
                    'SELECT COUNT(*) AS total FROM artist', artist['table'], schema))
                _, count_rows = step('sql_count_execute', lambda: execute_sql(count_sql))
                total = int(count_rows[0][0])
                page_size = get_settings().max_sql_rows
                export_limit = min(total, 1000) if explicit_all else min(total, page_size)
                columns, rows, page_sqls = ['ArtistId', 'Name'], [], []
                last_id = 0
                while len(rows) < export_limit:
                    roster_sql, _ = step('sql_roster_validate', lambda: validate_sql(
                        f'SELECT ArtistId, Name FROM artist WHERE ArtistId > {last_id} '
                        f'ORDER BY ArtistId LIMIT {page_size}', artist['table'], schema))
                    page_columns, page = step('sql_roster_execute', lambda: execute_sql(roster_sql))
                    page_sqls.append(roster_sql)
                    if not page:
                        break
                    next_id = int(page[-1][0])
                    if next_id <= last_id:
                        raise AppError('SQL_PAGINATION_FAILED', '音乐家列表分页未能继续', 502)
                    columns = page_columns
                    rows.extend(page[:export_limit-len(rows)])
                    last_id = next_id
                    if not explicit_all or len(page) < page_size:
                        break
                names = '、'.join(str(row[1]) for row in rows)
                answer = f'共有 {total} 位音乐家（艺术家）。'
                if rows:
                    answer += f'以下是{("全部" if len(rows) == total else f"前 {len(rows)} 位")}：{names}。'
                if total > len(rows):
                    if explicit_all:
                        answer += f'为控制回复长度，本次最多列出 1000 位，还有 {total-len(rows)} 位未列出。'
                    else:
                        answer += f'默认展示 {page_size} 位，还有 {total-len(rows)} 位未列出；可以要求列出全部音乐家。'
                return {'success': True, 'question': question, 'answer': answer,
                        'need_clarification': False, 'sql': page_sqls[0] if page_sqls else count_sql,
                        'count_sql': count_sql, 'page_sqls': page_sqls,
                        'table': table, 'columns': columns, 'rows': rows, 'row_count': len(rows),
                        'total_count': total, 'sources': [], 'semantic': semantic, 'trace': trace,
                        'latency_ms': round((time.perf_counter()-start)*1000)}
        schema = schema or step('schema_load', load_schema)
        generated = step('sql_generate', lambda: chat_json(NL2SQL_SYSTEM, json.dumps({'schema': schema, 'question': canonical_question}, ensure_ascii=False)))
        if generated.get('need_clarification') is True:
            return {'success': True, 'question': question, 'need_clarification': True,
                    'answer': generated.get('message') or '当前仅支持单表查询，请调整问题。',
                    'sql': None, 'table': None, 'columns': [], 'rows': [], 'row_count': 0,
                    'sources': [], 'semantic': semantic, 'trace': trace, 'latency_ms': round((time.perf_counter()-start)*1000)}
        if not isinstance(generated.get('query'), dict):
            raise AppError('SQL_GENERATION_FAILED', '模型未返回合法结构化查询', 502)
        diagnostic['query'] = generated['query']
        compiled = step('query_compile', lambda: compile_query_dsl(
            generated['query'], schema, max_rows=get_settings().max_sql_rows))
        diagnostic['sql'] = compiled.sql[:12000]
        diagnostic['table'] = compiled.table[:128]
        sql, table = step('sql_validate', lambda: validate_sql(
            compiled.sql, compiled.table, schema))
        executable_sql = render_pymysql_sql(sql)
        diagnostic['sql'] = sql
        diagnostic['table'] = table
        if compiled.params:
            columns, rows = step('sql_execute', lambda: execute_sql(executable_sql, compiled.params))
        else:
            columns, rows = step('sql_execute', lambda: execute_sql(executable_sql))
        def generate_answer():
            simple = _format_simple_answer(question, sql, table, columns, rows)
            if simple:
                return simple, {'guarded': False}
            guarded = generate_guarded_answer(question, sql, columns, rows, chat_fn=chat)
            return guarded['answer'], guarded
        answer, answer_guard = step('answer_generate', generate_answer)
        return {'success': True, 'question': question, 'answer': answer,
                'answer_guard': answer_guard, 'need_clarification': False,
                'sql': sql, 'table': table, 'columns': columns, 'rows': rows, 'row_count': len(rows),
                'sources': [], 'semantic': semantic, 'trace': trace, 'latency_ms': round((time.perf_counter()-start)*1000)}
    except Exception as error:
        attach_error_context(error)
        raise

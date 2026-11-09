"""Run bounded, live five-turn memory chains for all conversation modes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.budget import request_budget
from app.conversation import service, store
from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import AppError
from app.db.mysql import connection as database_connection
from app.services.document_service import (delete_document, import_document,
    index_document, list_documents, original_file_path)


PROJECT_ROOT = BACKEND_DIR.parent
DEMO_PDF = PROJECT_ROOT / 'docs' / 'demo.pdf'
CASE_FILE = BACKEND_DIR / 'tests' / 'cases' / 'conversation_memory_cases.json'
ORACLE_SQL = {
    'all_genres_count': 'SELECT COUNT(*) AS value FROM Genre',
    'all_genres': 'SELECT Name FROM Genre ORDER BY GenreId',
    'r_genres': "SELECT Name FROM Genre WHERE Name LIKE 'R%' ORDER BY GenreId",
    'r_genres_top5': "SELECT Name FROM Genre WHERE Name LIKE 'R%' ORDER BY Name LIMIT 5",
    'r_genres_count': "SELECT COUNT(*) AS value FROM Genre WHERE Name LIKE 'R%'",
    'r_genres_first': "SELECT Name FROM Genre WHERE Name LIKE 'R%' ORDER BY Name LIMIT 1",
}


def _oracle_rows(key: str) -> list[list]:
    with database_connection() as conn, conn.cursor() as cursor:
        cursor.execute(ORACLE_SQL[key])
        return [list(row) for row in cursor.fetchall()]


def _flatten_rows(rows) -> list[str]:
    values = []
    for row in rows or []:
        if isinstance(row, dict):
            values.extend(str(value) for value in row.values())
        elif isinstance(row, (list, tuple)):
            values.extend(str(value) for value in row)
        else:
            values.append(str(row))
    return values


def score_database_case(case: dict, result: dict, oracle_rows: list[list]) -> tuple[bool, dict]:
    actual_rows = result.get('rows') or []
    actual_values = _flatten_rows(actual_rows)
    table = str(result.get('table') or '').casefold()
    expected_rows = [tuple(str(value) for value in row) for row in oracle_rows]
    normalized_rows = [tuple(str(value) for value in row) for row in actual_rows
                       if isinstance(row, (list, tuple))]
    if case['oracle'] in {'r_genres_top5', 'r_genres_first'}:
        # These questions explicitly ask for an ordering, so order is part of the answer.
        values_match = normalized_rows == expected_rows
    else:
        # Unordered result sets must match exactly; extras and duplicates are inaccurate too.
        values_match = sorted(normalized_rows) == sorted(expected_rows)
    sql = str(result.get('sql') or '')
    passed = (bool(result.get('success')) and not result.get('need_clarification')
              and table == 'genre' and bool(sql.strip())
              and len(normalized_rows) == len(actual_rows) and values_match)
    return passed, {'table': table, 'row_count': len(actual_rows),
                    'sql_present': bool(sql.strip()), 'expected_values': [list(row) for row in expected_rows],
                    'actual_values': actual_values[:40], 'exact_result_match': values_match}


def score_material_case(case: dict, result: dict,
                        selected_document_id: str | None = None) -> tuple[bool, dict]:
    answer = str(result.get('answer') or '')
    sources = result.get('sources') or []
    pages = sorted({source.get('page') for source in sources if isinstance(source, dict)})
    source_text = '\n'.join(str(source.get('text') or '') for source in sources if isinstance(source, dict))
    keywords_ok = all(keyword.casefold() in answer.casefold() for keyword in case.get('keywords', []))
    source_keywords_ok = all(keyword.casefold() in source_text.casefold()
                             for keyword in case.get('keywords', []))
    cited_document_ids = {source.get('document_id') for source in sources
                          if isinstance(source, dict) and source.get('document_id')}
    scope_ids = result.get('document_ids')
    scope_ok = (scope_ids == [selected_document_id]
                and cited_document_ids == {selected_document_id}) if selected_document_id else bool(sources)
    passed = (bool(result.get('success')) and bool(answer.strip())
              and case['page'] in pages and keywords_ok and source_keywords_ok and scope_ok)
    return passed, {'pages': pages, 'expected_page': case['page'],
                    'keywords_in_answer': keywords_ok, 'keywords_in_cited_source': source_keywords_ok,
                    'cited_document_ids': sorted(cited_document_ids), 'scope_valid': scope_ok}


def score_agent_case(case: dict, result: dict, selected_document_id: str | None = None,
                     oracle_rows: list[list] | None = None) -> tuple[bool, dict]:
    answer = str(result.get('answer') or '')
    evidence = result.get('evidence') or []
    typed_evidence = [item for item in evidence if isinstance(item, dict)]
    sources = {item.get('source_type') for item in typed_evidence}
    document_evidence = [item for item in typed_evidence if item.get('source_type') == 'document']
    database_evidence = [item for item in typed_evidence if item.get('source_type') == 'database']
    pages = sorted({(item.get('provenance') or {}).get('page') for item in document_evidence
                    if isinstance(item, dict) and item.get('source_type') == 'document'})
    keywords_ok = all(keyword.casefold() in answer.casefold() for keyword in case.get('keywords', []))
    source_text = json.dumps(typed_evidence, ensure_ascii=False, default=str)
    evidence_values_ok = all(keyword.casefold() in source_text.casefold()
                             for keyword in case.get('keywords', []))
    required_sources_ok = set(case['sources']).issubset(sources)
    page_ok = case.get('page') is None or case['page'] in pages
    scope_ids = result.get('document_ids')
    cited_document_ids = {(item.get('provenance') or {}).get('document_id') for item in document_evidence}
    cited_scope_ok = (cited_document_ids == {selected_document_id}
                      if 'document' in case['sources'] else not cited_document_ids)
    scope_ok = (scope_ids == [selected_document_id] and cited_scope_ok) if selected_document_id else True
    source_keywords = case.get('source_keywords') or {}
    database_text = json.dumps(database_evidence, ensure_ascii=False, default=str).casefold()
    document_text = json.dumps(document_evidence, ensure_ascii=False, default=str).casefold()
    source_keywords_ok = (all(term.casefold() in database_text for term in source_keywords.get('database', []))
                          and all(term.casefold() in document_text for term in source_keywords.get('document', [])))
    database_rows = []
    for item in database_evidence:
        content = item.get('content')
        if isinstance(content, dict):
            database_rows.extend(content.get('rows') or [])
    database_sql_valid = True
    if 'database' in case['sources']:
        database_sql_valid = any(
            bool((item.get('provenance') or {}).get('sql'))
            and 'genre' in [str(table).casefold() for table in
                            (item.get('provenance') or {}).get('tables', [])]
            for item in database_evidence)
        if oracle_rows is not None:
            expected_rows = sorted(tuple(str(value) for value in row) for row in oracle_rows)
            actual_rows = sorted(tuple(str(value) for value in row)
                                 for row in database_rows if isinstance(row, (list, tuple)))
            database_sql_valid = database_sql_valid and len(actual_rows) == len(database_rows) \
                and actual_rows == expected_rows
    passed = (bool(result.get('success')) and bool(answer.strip()) and required_sources_ok
              and page_ok and keywords_ok and evidence_values_ok and scope_ok
              and source_keywords_ok and database_sql_valid)
    return passed, {'source_types': sorted(source for source in sources if source),
                    'required_sources': case['sources'], 'pages': pages,
                    'keywords_in_answer': keywords_ok, 'keywords_in_evidence': evidence_values_ok,
                    'source_keywords_valid': source_keywords_ok, 'scope_valid': scope_ok,
                    'database_sql_and_rows_valid': database_sql_valid,
                    'cited_document_ids': sorted(item for item in cited_document_ids if item)}


def _saved_sources(result: dict) -> list[dict]:
    sources = result.get('evidence') or result.get('sources') or []
    rows = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        provenance = source.get('provenance') or {}
        rows.append({
            'source_type': source.get('source_type', 'document'),
            'source_name': source.get('source_name') or source.get('filename'),
            'document_id': source.get('document_id') or provenance.get('document_id'),
            'page': source.get('page') or provenance.get('page'),
            'locator': source.get('locator') or provenance.get('locator'),
            'sql': provenance.get('sql'),
            'content': source.get('content') or source.get('text'),
        })
    return rows


def chain_summary(turns: list[dict]) -> dict:
    passed = sum(bool(turn.get('passed')) for turn in turns)
    total = len(turns)
    return {'passed': passed, 'cases': total,
            'accuracy': passed / total if total else 0,
            'five_turn_passed': total >= 5 and all(turn.get('passed') for turn in turns[:5])}


def _fixture_pdf_id() -> tuple[str, bool]:
    if not DEMO_PDF.is_file():
        raise RuntimeError('缺少仓库固定材料 docs/demo.pdf')
    expected_hash = hashlib.sha256(DEMO_PDF.read_bytes()).hexdigest()
    for document in list_documents():
        if document.get('status') != 'indexed':
            continue
        try:
            path, _ = original_file_path(document['document_id'])
            if hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash:
                return document['document_id'], False
        except (OSError, AppError):
            continue
    imported = import_document(DEMO_PDF.read_bytes(), 'conversation-memory-demo.pdf')
    try:
        index_document(imported['document_id'])
    except Exception:
        delete_document(imported['document_id'])
        raise
    return imported['document_id'], True


def run_live(max_api_requests: int, context_limit_tokens: int, output: Path) -> dict:
    settings = get_settings()
    if not settings.deepseek_api_key.get_secret_value():
        raise RuntimeError('未配置 DeepSeek API Key')
    if settings.mysql_database.casefold() != 'chinook':
        raise RuntimeError('连续对话基准要求使用 Chinook MySQL 数据库')
    cases = json.loads(CASE_FILE.read_text(encoding='utf-8'))
    if any(len(cases.get(mode, [])) < 5 for mode in ('database', 'rag', 'agent')):
        raise RuntimeError('固定对话评测集必须为每种模式至少提供五轮')

    fixture_id, temporary_fixture = _fixture_pdf_id()
    owner_id = 'memory_eval_' + uuid.uuid4().hex[:32]
    conversation_ids = []
    report = {'mode': 'live', 'model': settings.deepseek_model,
              'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'context_limit_tokens': context_limit_tokens,
              'api_request_cap': max_api_requests, 'fixture': 'docs/demo.pdf',
              'chains': {}, 'llm_usage': {key: 0 for key in
                  ('api_requests', 'reported_requests', 'prompt_tokens', 'completion_tokens')},
              'unreported_usage_requests': 0}
    actual_requests = 0
    try:
        oracles = {key: _oracle_rows(key) for key in ORACLE_SQL}
        with request_budget(max_api_requests, settings.llm_timeout, context_limit_tokens) as budget:
            for mode, mode_cases in cases.items():
                if mode not in {'database', 'rag', 'agent'}:
                    continue
                document_id = fixture_id if mode in {'rag', 'agent'} else None
                conversation = store.create(owner_id, mode, document_id)
                conversation_id = conversation['id']
                conversation_ids.append(conversation_id)
                turn_rows = []
                for index, case in enumerate(mode_cases[:5], 1):
                    attempt_start = budget.used
                    try:
                        result = service.ask(owner_id, conversation_id, case['question'],
                            document_ids=[fixture_id] if mode in {'rag', 'agent'} else None,
                            context_limit_tokens=context_limit_tokens)
                        if mode == 'database':
                            passed, details = score_database_case(case, result, oracles[case['oracle']])
                        elif mode == 'rag':
                            passed, details = score_material_case(case, result, fixture_id)
                        else:
                            agent_oracle = oracles.get(case.get('database_oracle'))
                            passed, details = score_agent_case(case, result, fixture_id, agent_oracle)
                        item = {'turn': index, 'question': case['question'], 'passed': passed,
                                'answer': result.get('answer'),
                                'resolved_question': result.get('resolved_question'),
                                'expected': case,
                                'document_ids': result.get('document_ids'),
                                'table': result.get('table'), 'rows': result.get('rows'),
                                'sql': result.get('sql'), 'sources': _saved_sources(result),
                                'details': details, 'context_usage': result.get('context_usage')}
                    except Exception as error:
                        item = {'turn': index, 'question': case['question'], 'passed': False,
                                'error': getattr(error, 'code', type(error).__name__),
                                'details': {}}
                    item['api_requests'] = budget.used - attempt_start
                    turn_rows.append(item)
                    actual_requests = budget.used
                    if budget.used >= max_api_requests:
                        for remaining in mode_cases[index:5]:
                            turn_rows.append({'turn': len(turn_rows) + 1,
                                'question': remaining['question'], 'passed': False,
                                'error': 'API_REQUEST_CAP_REACHED', 'api_requests': 0})
                        break
                report['chains'][mode] = {**chain_summary(turn_rows), 'turns': turn_rows}
                if budget.used >= max_api_requests:
                    break
        report['api_requests'] = actual_requests
        report['summaries'] = {mode: {key: value for key, value in chain.items() if key != 'turns'}
                               for mode, chain in report['chains'].items()}
        report['five_turn_chains_passed'] = sum(
            bool(chain.get('five_turn_passed')) for chain in report['chains'].values())
        report['five_turn_chain_count'] = 3
        report['continuous_five_turn_requirement_met'] = report['five_turn_chains_passed'] == 3
        for chain in report['chains'].values():
            for turn in chain['turns']:
                usage = turn.get('context_usage') or {}
                report['llm_usage']['api_requests'] += usage.get('api_requests') or 0
                report['llm_usage']['reported_requests'] += usage.get('reported_requests') or 0
                report['llm_usage']['prompt_tokens'] += usage.get('total_prompt_tokens') or 0
                report['llm_usage']['completion_tokens'] += usage.get('total_completion_tokens') or 0
        report['unreported_usage_requests'] = max(
            0, actual_requests - report['llm_usage']['reported_requests'])
        report['llm_usage']['api_requests'] = actual_requests
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    finally:
        for conversation_id in conversation_ids:
            try:
                store.delete(owner_id, conversation_id)
            except AppError:
                pass
        if temporary_fixture:
            try:
                delete_document(fixture_id)
            except AppError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description='Run five-turn live context-memory chains for database, RAG, and agent modes.')
    parser.add_argument('--live', action='store_true', help='call the configured model API; otherwise print a zero-request plan')
    parser.add_argument('--max-api-requests', type=int, help='hard request-attempt cap across all three chains, including retries')
    parser.add_argument('--context-limit-tokens', type=int, help='input-token budget applied to every turn')
    parser.add_argument('--output', type=Path, default=BACKEND_DIR / 'data/evaluation/conversation-memory.json')
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({'mode': 'preview_only', 'chains': {'database': 5, 'rag': 5, 'agent': 5},
                          'api_requests': 0, 'next_step': 'add --live with both --max-api-requests and --context-limit-tokens'},
                         ensure_ascii=False))
        return 0
    if not args.max_api_requests or not 1 <= args.max_api_requests <= 2000:
        parser.error('--live requires --max-api-requests between 1 and 2000')
    if not args.context_limit_tokens or not 1000 <= args.context_limit_tokens <= 50000:
        parser.error('--live requires --context-limit-tokens between 1000 and 50000')
    try:
        report = run_live(args.max_api_requests, args.context_limit_tokens, args.output)
    except Exception as error:
        print(json.dumps({'mode': 'live', 'complete': False,
                          'error': getattr(error, 'code', type(error).__name__),
                          'message': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({'mode': report['mode'], 'summaries': report['summaries'],
                      'api_requests': report['api_requests'], 'api_request_cap': report['api_request_cap'],
                      'llm_usage': report['llm_usage'],
                      'unreported_usage_requests': report['unreported_usage_requests'],
                      'continuous_five_turn_requirement_met': report['continuous_five_turn_requirement_met'],
                      'output': str(args.output)}, ensure_ascii=False))
    return 0 if report['continuous_five_turn_requirement_met'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

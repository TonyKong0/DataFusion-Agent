"""Reproducible agent evaluation.

Default mode is offline: routing/planning with synthetic tools, no LLM requests.
``--live`` switches to real LLM routing and real tool execution, and therefore
requires an explicit API request cap. Live mode grades answers against a
human-annotated golden set (``tests/golden_answers_v1.7.json`` by default;
``tests/golden_answers_v1.8.json`` is the human-confirmed layered set;
numeric/contains/reject matching, 1% tolerance on numbers).

v1.8 additions (all optional, default behaviour unchanged):
* ``--golden`` loads a layered v1.8 set; a draft (not human-confirmed) set can
  be exercised for debugging but is flagged ``metrics_eligible=False`` so it
  can never be mistaken for a human-annotated measurement.  S2-C clarification
  cases are excluded from live_answer_accuracy and reported as reject_correctness.
* ``judge_citation`` / ``judge_faithfulness`` produce per-case evidence for
  citation accuracy and answer faithfulness. Both compare answers against
  human-confirmed criteria automatically; they are not semantic human scores.
* cold/warm latency phases are recorded per execution case and summarised
  separately, so the BGE-M3 cold start no longer pollutes the stable mean.
"""
import json
import argparse
import re
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_agent_phase50_eval import DB_CASES, DOC_CASES, DOC_DB, DB_DOC, PARALLEL, FORMULA, CLARIFY
from app.agent.router import route_query
from app.agent.planner import create_plan
from app.agent.models import ToolResult
from app.agent.service import query
from app.core.config import get_settings
from app.llm.usage import collect_usage
from app.services.answer_semantic_guard import guard_answer, sql_semantics

DEFAULT_LIVE_CASES = 10
GOLDEN_FILE = ROOT / 'tests' / 'golden_answers_v1.7.json'
GOLDEN_DRAFT_V18 = ROOT / 'tests' / 'golden_answers_v1.8.draft.json'
GOLDEN_CONFIRMED_V18 = ROOT / 'tests' / 'golden_answers_v1.8.json'
REJECT_MARKERS = ('无法', '不足', '未找到', '没有找到', '不能确认', '无法确认', '未提供', '未包含', '未记录')
CLARIFY_MARKERS = ('请明确', '请补充', '请说明', '请指定', '需要更多信息', '需要明确',
                   '请提供', '无法确定范围', '信息不足', '无法确认答案')
NUMBER_PATTERN = re.compile(r'\d[\d,]*(?:\.\d+)?')
NUMERIC_TOLERANCE = 0.01
LAYER_ORDER = ('S1', 'S2-A', 'S2-B', 'S2-C')

# Fixed, text-bearing materials for v1.8 citation grading.  The PDF
# 02_service_policy_example.pdf has no text layer and 03_ocr-sign.png indexes
# only a single OCR marker line; neither can support citation judgement.
EVALUATION_MATERIALS = ('07_store_faq.txt', '08_chinook_data_dictionary.md',
                        '04_invoice_review_example.docx')
EXCLUDED_MATERIALS_NOTE = (
    '02_service_policy_example.pdf 为无文字层 PDF（PyMuPDF 抽取为空），'
    '03_ocr-sign.png 索引内容仅一行 OCR 标记；两者不用于引用判分。')


def load_golden_cases(path: Path | None = None) -> dict[str, dict]:
    """Return golden cases keyed by question text."""
    data = json.loads((path or GOLDEN_FILE).read_text(encoding='utf-8'))
    return {case['question']: case for case in data['cases']}


def load_golden_meta(path: Path | None = None) -> dict:
    """Return set-level metadata, including whether a human confirmed it."""
    data = json.loads((path or GOLDEN_FILE).read_text(encoding='utf-8'))
    return {key: value for key, value in data.items() if key != 'cases'}


def golden_metrics_eligible(meta: dict, load_error: str | None = None) -> bool:
    """Only a human-confirmed set may feed metrics.json or the report.

    v1.7 predates the explicit ``status`` field but records a human annotator
    and date; v1.8 drafts carry ``status=pending_human_confirmation``.
    """
    if load_error is not None:
        return False
    status = meta.get('status')
    if status is not None:
        return status == 'human-confirmed'
    return (str(meta.get('annotator') or '').startswith('human-confirmed')
            and meta.get('annotated_at') is not None)


def _extract_numbers(text: str) -> list[float]:
    return [float(match.replace(',', '')) for match in NUMBER_PATTERN.findall(text)]


def _mentions_document_absence(answer: str) -> bool:
    mentions_doc = '文档' in answer or '材料' in answer
    return mentions_doc and any(marker in answer for marker in ('未', '无', '不'))


def _numeric_matched(answer: str, golden: float | None) -> bool:
    if golden is None:
        return True
    numbers = _extract_numbers(answer)
    return any(abs(number - golden) <= max(0.01, abs(golden) * NUMERIC_TOLERANCE)
               for number in numbers)


def _refuses_to_answer(answer: str) -> bool:
    return not answer.strip() or any(marker in answer for marker in REJECT_MARKERS)


def _asks_for_clarification(answer: str) -> bool:
    return any(marker in answer for marker in CLARIFY_MARKERS)


def _document_side_expected(case: dict) -> bool:
    """Whether the case legitimately involves the document side.

    Derived only from human-confirmed golden fields, never from the model's
    answer: an explicit target document / expected citation, or a question
    mentioning 文档 / 材料.  Pure database single-source questions (S2-A)
    carry none of these, so requiring a document-side note for them is a
    grading-contract defect rather than a system defect.
    """
    question = str(case.get('question') or '')
    return bool(case.get('target_document') or case.get('expected_citation')
                or '文档' in question or '材料' in question)


def judge_answer(answer: str, case: dict, contract: str = 'legacy') -> dict:
    """Grade one answer against its golden case; returns verdict / matched / reason.

    ``contract='legacy'`` reproduces every historical result byte-for-byte.
    ``contract='revised'`` lifts the document-side note condition for cases
    whose confirmed criteria show no document involvement (see 4.11 in the
    report); all other grading rules, and the golden set itself, are unchanged.
    """
    if contract not in ('legacy', 'revised'):
        raise ValueError(f'unknown grading contract: {contract}')
    match_type = case.get('match_type')
    if match_type in ('reject*', 'clarify'):
        clarified = _asks_for_clarification(answer)
        return {'verdict': 'correct' if clarified else 'wrong', 'matched': clarified,
                'reason': '应澄清且回答含澄清语义' if clarified else '应澄清但模型直接给出了结论'}
    if match_type == 'reject':
        refused = _refuses_to_answer(answer)
        return {'verdict': 'correct' if refused else 'wrong', 'matched': refused,
                'reason': '应拒答且回答含拒答语义' if refused else '应拒答但模型给出了具体答案'}
    if not answer.strip():
        return {'verdict': 'wrong', 'matched': False, 'reason': '空回答'}
    doc_required = (contract != 'revised' or _document_side_expected(case))
    doc_absence = _mentions_document_absence(answer)
    doc_note_ok = doc_absence or not doc_required
    if match_type == 'numeric':
        golden = case.get('golden_numeric')
        if not _numeric_matched(answer, golden):
            return {'verdict': 'wrong', 'matched': False, 'reason': f'数值与黄金值 {golden} 不符'}
        if doc_note_ok:
            reason = ('数值正确并说明文档未记录' if doc_required else
                      '数值正确；判据显示本题不涉及文档侧，按事实正确性计分')
            return {'verdict': 'correct', 'matched': True, 'reason': reason}
        return {'verdict': 'partial', 'matched': False, 'reason': '数值正确但未说明文档侧情况'}
    if match_type == 'contains':
        accepted = [case['golden']] + ([case['golden_alt']] if case.get('golden_alt') else [])
        name_hit = any(name in answer for name in accepted)
        if not name_hit:
            return {'verdict': 'wrong', 'matched': False, 'reason': f'答案未包含黄金名称 {accepted[0]}'}
        numeric_ok = _numeric_matched(answer, case.get('golden_numeric'))
        if not numeric_ok:
            return {'verdict': 'partial', 'matched': False, 'reason': '名称正确但数值与黄金值不符'}
        if doc_note_ok:
            reason = ('名称与数值正确并说明文档无描述' if doc_required else
                      '名称与数值正确；判据显示本题不涉及文档侧，按事实正确性计分')
            return {'verdict': 'correct', 'matched': True, 'reason': reason}
        return {'verdict': 'partial', 'matched': False, 'reason': '名称与数值正确但未说明文档侧情况'}
    return {'verdict': 'wrong', 'matched': False, 'reason': f'未知 match_type: {match_type}'}


def _document_sources(output: dict) -> list[dict]:
    """Structured document evidence, used for citation grading and回源."""
    sources = []
    for item in output.get('evidence') or []:
        if item.get('source_type') not in ('document', 'text', 'version_diff'):
            continue
        provenance = item.get('provenance') or {}
        locator = provenance.get('locator') or '/'.join(
            str(part) for part in provenance.get('heading_path') or [])
        sources.append({'source_name': item.get('source_name'),
                        'page': provenance.get('page'), 'locator': locator,
                        'text': str(item.get('content') or provenance.get('text') or '')[:1200]})
    return sources


def judge_citation(answer: str, case: dict, document_sources: list[dict]) -> dict:
    """Whether the cited material is the expected one and its text supports the claim.

    ``None`` = not in this metric's denominator; ``'no_claim'`` = the answer
    offers no citation at all (reported separately, never folded into the
    denominator); True/False = supported / unsupported.
    """
    expected = case.get('expected_citation')
    if not expected:
        return {'citation_supported': None, 'reason': '未标注应引用出处，不进入分母',
                'cited_documents': []}
    cited = [str(item['source_name']) for item in document_sources if item.get('source_name')]
    for name in EVALUATION_MATERIALS:
        if name in answer and name not in cited:
            cited.append(name)
    if not cited and not re.search(r'文档第\s*\d+\s*页|第\s*\d+\s*页|材料|出处', answer):
        return {'citation_supported': 'no_claim', 'reason': '回答未给出任何引用线索',
                'cited_documents': []}
    expected_names = [name for name in EVALUATION_MATERIALS if name in str(expected)]
    if not expected_names:
        expected_names = re.findall(r'[\w\-]+\.(?:txt|md|docx|pdf|png|jpg|csv)', str(expected))
    if not expected_names:
        return {'citation_supported': None, 'reason': '应引用出处无法解析为文件名',
                'cited_documents': cited}
    matched_document = any(any(expected_name in cited_name or cited_name in expected_name
                               for expected_name in expected_names)
                           for cited_name in cited)
    corpus = '\n'.join(f"{item.get('text') or ''} {item.get('locator') or ''}"
                       for item in document_sources)
    facts = case.get('citation_facts') or []
    fact_hits = [fact for fact in facts if fact in corpus]
    supported = bool(matched_document) and (not facts or bool(fact_hits))
    reason = ('引用指向应引用材料且原文含对应事实' if supported else
              '引用未指向应引用材料' if not matched_document else
              '引用材料正确但原文未检出对应事实')
    return {'citation_supported': supported, 'matched_document': matched_document,
            'expected_documents': expected_names, 'cited_documents': cited,
            'fact_hits': fact_hits, 'reason': reason}


def judge_faithfulness(answer: str, case: dict, sqls: list[str] | None = None) -> dict:
    """Whether the answer stays within human-confirmed evidence boundaries."""
    forbidden = case.get('forbidden_claims') or []
    hits = [phrase for phrase in forbidden if phrase and phrase in answer]
    sql_overreach = False
    for sql in sqls or []:
        tags = sql_semantics(sql)
        if tags.get('comparison_level') == 'row_level':
            sql_overreach = sql_overreach or guard_answer(
                answer, sql, semantics=tags)['guarded']
    if not forbidden and not sqls:
        return {'faithful': None, 'reason': '无禁止措辞判据且无 SQL 语义证据，不进入分母',
                'matched_forbidden': [], 'sql_overreach': False}
    faithful = not hits and not sql_overreach
    detail = []
    if hits:
        detail.append(f'命中禁止措辞 {hits}')
    if sql_overreach:
        detail.append('把行级比较表述为聚合级结论')
    return {'faithful': faithful, 'matched_forbidden': hits,
            'sql_overreach': sql_overreach,
            'reason': '；'.join(detail) if detail else '未出现越界结论'}


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[int(fraction * (len(ordered) - 1))], 2)


def summarize_latencies(execution_rows: list[dict]) -> dict:
    """Split the first (cold-start) case from the warm distribution."""
    valid = [row for row in execution_rows
             if isinstance(row.get('latency_ms'), (int, float))]
    cold = [row for row in valid if row.get('phase') == 'cold']
    warm = [row for row in valid if row.get('phase') == 'warm']

    def stats(rows):
        values = [float(row['latency_ms']) for row in rows]
        return {'count': len(values),
                'mean_ms': round(sum(values) / len(values), 2) if values else None,
                'p50_ms': _percentile(values, .5), 'p95_ms': _percentile(values, .95)}

    return {'all': stats(valid), 'cold': stats(cold), 'warm': stats(warm),
            'cold_start_latency_ms': (float(cold[0]['latency_ms']) if cold else None),
            'cold_start_case': cold[0].get('question') if cold else None,
            'note': ('冷启动按执行序位判定：第 1 个执行用例承担 BGE-M3 首次加载；'
                     '这是序位口径而非精确归因，热态统计不含该例。')}


def fake_tool(name, question, context):
    if name == 'database_query':
        value = 'Rock' if '销量最高' in question else 3
        return ToolResult(name, True, {'sql': 'SELECT COUNT(*) AS value FROM Invoice',
            'columns': ['value'], 'rows': [[value]], 'row_count': 1})
    if name == 'document_search':
        return ToolResult(name, True, {'document_id': 'doc_eval', 'answer': '审核阈值为 500',
            'sources': [{'chunk_id': 'chunk_eval', 'page': 2, 'heading_path': ['审核'],
                         'text': '审核阈值为 500 元。', 'score': .9}]})
    if name == 'formula_calculate':
        return ToolResult(name, True, {'result': 0.2, 'expression': '(a-b)/b',
            'parameter_source': 'database', 'database_sql': 'SELECT COUNT(*) AS value FROM Invoice',
            'parameters': [{'name': 'a', 'normalized_value': 12}, {'name': 'b', 'normalized_value': 10}],
            'source': {'document_id': 'doc_eval', 'page': 3, 'heading_path': ['计算'],
                       'chunk_id': 'formula_eval', 'text': '增长率=(本期-上期)/上期'}})
    return ToolResult(name, True, {'question': '请明确数据源'})


def run():
    categories = [('database', DB_CASES, 'DATABASE_ONLY'), ('document', DOC_CASES, 'DOCUMENT_ONLY'),
                  ('document_to_database', DOC_DB, 'CROSS_SOURCE'),
                  ('database_to_document', DB_DOC, 'CROSS_SOURCE'),
                  ('parallel', PARALLEL, 'CROSS_SOURCE'), ('formula', FORMULA, 'CROSS_SOURCE'),
                  ('clarification', CLARIFY, 'CLARIFICATION_REQUIRED')]
    rows = []
    for label, cases, expected in categories:
        for question in cases:
            start = perf_counter()
            routed = route_query(question, allow_llm=False)
            plan = create_plan(question, routed)
            rows.append({'category': label, 'question': question, 'route_ok': routed['route'] == expected,
                         'plan_valid': bool(plan.steps), 'routing_planning_ms': (perf_counter() - start) * 1000})
    outputs = []
    with patch('app.agent.executor.call_tool', fake_tool), patch('app.agent.service.list_documents', lambda: []):
        for label, cases, _ in categories[2:6]:
            for question in cases:
                output = query(question, 'doc_eval', allow_router_llm=False)
                outputs.append({'category': label, 'complete': output['execution']['status'] == 'success',
                                'source_coverage': {e['source_type'] for e in output['evidence']} >= {'database', 'document'},
                                'citation_valid': all(set(claim['evidence_ids']) <=
                                    {e['evidence_id'] for e in output['evidence']} for claim in output['claims']),
                                'latency_ms': output['latency']['total_ms'],
                                'llm_calls': output['latency']['llm_calls']})
    latencies = sorted(row['latency_ms'] for row in outputs)
    result = {'scope': 'offline routing/planning and synthetic-tool orchestration',
              'cases': {label: len(cases) for label, cases, _ in categories},
              'routing_accuracy': sum(row['route_ok'] for row in rows) / len(rows),
              'plan_valid_rate': sum(row['plan_valid'] for row in rows) / len(rows),
              'synthetic_tool_plan_completion': sum(row['complete'] for row in outputs) / len(outputs),
              'synthetic_source_coverage': sum(row['source_coverage'] for row in outputs) / len(outputs),
              'synthetic_citation_valid_rate': sum(row['citation_valid'] for row in outputs) / len(outputs),
              'synthetic_avg_latency_ms': round(sum(latencies) / len(latencies), 2),
              'synthetic_p95_latency_ms': round(latencies[int(.95 * (len(latencies)-1))], 2),
              'synthetic_avg_llm_calls': sum(row['llm_calls'] for row in outputs) / len(outputs),
              'live_answer_accuracy': None, 'live_cross_source_answer_accuracy': None}
    return result


def _environment() -> tuple[bool, list[str]]:
    """Report whether the live dependencies are actually present."""
    from app.db.mysql import database_status
    from app.services.document_service import list_documents
    from app.services.vector_store import ready
    try:
        database_status()
        mysql_ready = True
    except Exception:
        mysql_ready = False
    try:
        document_ids = [document['document_id'] for document in list_documents()
                        if ready(document['document_id'])]
    except Exception:
        document_ids = []
    return mysql_ready, document_ids


def _evaluation_materials() -> list[dict]:
    """Resolve the fixed, indexed text materials to their document ids."""
    from app.services.document_service import list_documents
    from app.services.vector_store import ready
    try:
        documents = list_documents()
    except Exception:
        return []
    matched = []
    for document in documents:
        filename = document.get('filename') or ''
        try:
            indexed = ready(document['document_id'])
        except Exception:
            indexed = False
        if indexed and filename in EVALUATION_MATERIALS:
            matched.append({'document_id': document['document_id'], 'filename': filename})
    return sorted(matched, key=lambda item: EVALUATION_MATERIALS.index(item['filename']))


def _citation_structurally_valid(output: dict) -> bool:
    evidence_ids = {item['evidence_id'] for item in output.get('evidence', [])}
    claims = output.get('claims') or []
    return bool(claims) and all(set(claim.get('evidence_ids') or []) <= evidence_ids
                                for claim in claims)


def _execution_sample(categories, mysql_ready: bool, document_ids: list[str],
                      live_cases: int) -> tuple[list[tuple[str, str]], str | None]:
    """Pick a deterministic, category-interleaved subset the environment can run."""
    if mysql_ready and document_ids:
        pools = [(label, cases) for label, cases, _ in categories[2:6]]
        pool, note = [], None
    elif mysql_ready:
        pools = [(label, cases) for label, cases, _ in categories[:1]]
        pool, note = [], '缺少已索引材料，跨源执行抽样改为数据库问答抽样'
    else:
        return [], '需要 MySQL 与至少一份已索引材料，本机环境未满足，未做真实执行抽样'
    index = 0
    while len(pool) < live_cases and any(index < len(cases) for _, cases in pools):
        for label, cases in pools:
            if index < len(cases) and len(pool) < live_cases:
                pool.append((label, cases[index]))
        index += 1
    return pool, note


def _layered_sample(cases: dict[str, dict], live_cases: int) -> list[dict]:
    """Interleave the four v1.8 layers so every layer enters live execution."""
    pools = {layer: [case for case in cases.values() if case.get('layer') == layer]
             for layer in LAYER_ORDER}
    sample, index = [], 0
    while len(sample) < live_cases and any(index < len(pool) for pool in pools.values()):
        for layer in LAYER_ORDER:
            if index < len(pools[layer]) and len(sample) < live_cases:
                sample.append(pools[layer][index])
        index += 1
    return sample


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _answer_accuracy_rows(execution_rows: list[dict]) -> list[dict]:
    """Rows entering live_answer_accuracy (26-case denominator in the v1.8 set).

    S2-C clarification/rejection cases are reported separately as
    reject_correctness, so they must not silently enlarge the accuracy
    denominator.  Non-layered v1.7 runs carry layer=None and stay unaffected.
    """
    return [row for row in execution_rows
            if row.get('verdict') is not None and row.get('layer') != 'S2-C']


def run_live(max_api_requests: int, live_cases: int = DEFAULT_LIVE_CASES,
             golden_path: Path | None = None,
             grading_contract: str = 'legacy') -> dict:
    if max_api_requests <= 0:
        raise ValueError('live measurement requires --max-api-requests > 0')
    settings = get_settings()
    mysql_ready, document_ids = _environment()
    materials = _evaluation_materials()
    fallback_document_id = (materials[0]['document_id'] if materials else
                            document_ids[0] if document_ids else None)
    material_ids = {item['filename']: item['document_id'] for item in materials}
    categories = [('database', DB_CASES, 'DATABASE_ONLY'), ('document', DOC_CASES, 'DOCUMENT_ONLY'),
                  ('document_to_database', DOC_DB, 'CROSS_SOURCE'),
                  ('database_to_document', DB_DOC, 'CROSS_SOURCE'),
                  ('parallel', PARALLEL, 'CROSS_SOURCE'), ('formula', FORMULA, 'CROSS_SOURCE'),
                  ('clarification', CLARIFY, 'CLARIFICATION_REQUIRED')]
    golden_error = None
    try:
        golden_cases = load_golden_cases(golden_path)
        golden_meta = load_golden_meta(golden_path)
    except Exception as error:  # noqa: BLE001 - keep the run alive, report the gap
        golden_cases, golden_meta, golden_error = {}, {}, type(error).__name__
    golden_name = (golden_path or GOLDEN_FILE).name
    golden_status = golden_meta.get('status', 'human-confirmed')
    metrics_eligible = golden_metrics_eligible(golden_meta, golden_error)
    usage = None
    routed_rows = []
    truncated = False
    with collect_usage() as collected:
        usage = collected
        for label, cases, expected in categories:
            for question in cases:
                if usage.api_requests >= max_api_requests:
                    truncated = True
                    break
                before = usage.api_requests
                start = perf_counter()
                routed = route_query(question, allow_llm=True,
                                     selected_document_count=len(document_ids))
                plan = create_plan(question, routed)
                routed_rows.append({'category': label, 'question': question,
                                    'route_ok': routed['route'] == expected,
                                    'plan_valid': bool(plan.steps),
                                    'llm_fallback': usage.api_requests > before,
                                    'routing_planning_ms': (perf_counter() - start) * 1000})
            if truncated:
                break

        layered = golden_path is not None and golden_cases and all(
            case.get('layer') for case in golden_cases.values())
        if layered:
            sample = [{'question': case['question'], 'category': case.get('category'),
                       'layer': case.get('layer'), 'golden_case': case}
                      for case in _layered_sample(golden_cases, live_cases)]
            execution_note = (f'按 {golden_name} 四层分层抽样；'
                              '每题按 target_document 选择材料，数据库/澄清题不传材料。')
        else:
            pairs, execution_note = _execution_sample(categories, mysql_ready, document_ids, live_cases)
            sample = [{'question': question, 'category': label, 'layer': None,
                       'golden_case': golden_cases.get(question)}
                      for label, question in pairs]

        execution_rows = []
        for index, item in enumerate(sample):
            if usage.api_requests >= max_api_requests:
                truncated = True
                break
            question, case = item['question'], item.get('golden_case')
            target = (case or {}).get('target_document')
            selected_id = material_ids.get(target, fallback_document_id) if target else (
                None if (case or {}).get('layer') in ('S2-A', 'S2-C') else fallback_document_id)
            phase = 'cold' if index == 0 else 'warm'
            start = perf_counter()
            try:
                output = query(question, selected_id, allow_router_llm=True)
            except Exception as error:  # noqa: BLE001 - record the failure, do not hide it
                execution_rows.append({'category': item['category'], 'question': question,
                                       'layer': item['layer'], 'status': 'error',
                                       'completed': False, 'citation_structurally_valid': False,
                                       'answer_present': False, 'answer': '',
                                       'evidence_preview': [], 'claims': 0, 'evidence': 0,
                                       'document_sources': [], 'sqls': [],
                                       'document_id': selected_id,
                                       'cold_start': phase == 'cold', 'phase': phase,
                                       'latency_ms': round((perf_counter() - start) * 1000, 2),
                                       'llm_calls': 0, 'error': type(error).__name__})
                continue
            latency = output.get('latency') or {}
            execution = output.get('execution') or {}
            evidence_items = output.get('evidence') or []
            document_sources = _document_sources(output)
            sqls = [evidence_item['provenance']['sql'] for evidence_item in evidence_items
                    if evidence_item.get('source_type') == 'database'
                    and (evidence_item.get('provenance') or {}).get('sql')]
            execution_rows.append({
                'category': item['category'], 'question': question, 'layer': item['layer'],
                'status': execution.get('status'),
                'completed': execution.get('status') == 'success',
                'citation_structurally_valid': _citation_structurally_valid(output),
                'answer_present': bool((output.get('answer') or '').strip()),
                'answer': (output.get('answer') or '').strip()[:800],
                'evidence_preview': [str(source)[:160] for source in evidence_items[:2]],
                'claims': len(output.get('claims') or []),
                'evidence': len(evidence_items),
                'document_sources': document_sources,
                'sqls': sqls,
                'document_id': selected_id,
                'cold_start': phase == 'cold', 'phase': phase,
                'latency_ms': latency.get('total_ms'),
                'llm_calls': latency.get('llm_calls', 0),
                'error': None})

    latencies = sorted(row['latency_ms'] for row in execution_rows
                       if isinstance(row['latency_ms'], (int, float)))
    latency_summary = summarize_latencies(execution_rows)
    status_counts = {}
    for row in execution_rows:
        status_counts[row['status']] = status_counts.get(row['status'], 0) + 1
    verdict_counts = {}
    citation_rows, faithful_rows, reject_rows = [], [], []
    for row in execution_rows:
        case = golden_cases.get(row['question'])
        if case is None:
            row.update({'golden_match': None, 'verdict': None, 'verdict_reason': '无对应黄金条目'})
            continue
        judged = judge_answer(row.get('answer') or '', case, contract=grading_contract)
        row.update({'golden_match': judged['matched'], 'verdict': judged['verdict'],
                    'verdict_reason': judged['reason']})
        verdict_counts[judged['verdict']] = verdict_counts.get(judged['verdict'], 0) + 1
        if case.get('match_type') in ('reject*', 'clarify', 'reject') and case.get('layer') == 'S2-C':
            reject_rows.append(row)
        citation = judge_citation(row.get('answer') or '', case, row.get('document_sources') or [])
        faithfulness = judge_faithfulness(row.get('answer') or '', case, row.get('sqls') or [])
        # Only cases carrying a human-confirmed citation criterion enter the
        # two new metric denominators.  SQL-level checks on database-only cases
        # stay in the per-case detail as evidence for the semantic guard, but
        # must not silently enlarge the denominator.
        faithfulness['in_denominator'] = (bool(case.get('expected_citation'))
                                          or bool(case.get('faithfulness_eligible')))
        row['citation_judgement'] = citation
        row['faithfulness_judgement'] = faithfulness
        if citation['citation_supported'] is True or citation['citation_supported'] is False:
            citation_rows.append(citation)
        if (faithfulness['faithful'] is True or faithfulness['faithful'] is False) \
                and faithfulness['in_denominator']:
            faithful_rows.append(faithfulness)
    judged_rows = _answer_accuracy_rows(execution_rows)
    answer_accuracy = (sum(row['verdict'] == 'correct' for row in judged_rows) / len(judged_rows)
                       if judged_rows else None)
    answer_acceptable = (sum(row['verdict'] in ('correct', 'partial') for row in judged_rows)
                         / len(judged_rows) if judged_rows else None)
    result = {
        'scope': 'live routing, real tool execution, and golden-set answer grading',
        'cases': {label: len(cases) for label, cases, _ in categories},
        'environment': {'mysql': mysql_ready, 'indexed_documents': len(document_ids),
                        'model': settings.deepseek_model,
                        'evaluation_materials': list(EVALUATION_MATERIALS),
                        'indexed_material_matches': [item['filename'] for item in materials],
                        'fallback_document_id': fallback_document_id,
                        'document_selection_rule': (
                            '按 EVALUATION_MATERIALS 顺序固定选择已索引材料；'
                            '每题优先用 golden case 的 target_document，其余回退到首份材料；'
                            '数据库单源与澄清题不传材料。'),
                        'excluded_materials_note': EXCLUDED_MATERIALS_NOTE},
        'golden_set': {'file': golden_name, 'status': golden_status,
                       'metrics_eligible': metrics_eligible,
                       'load_error': golden_error,
                       'grading_note': ('人工确认判据 + 自动比对，不是逐题人工语义评分；'
                                        'draft 状态的结果不得回填 metrics.json。')},
        'grading_contract': grading_contract,
        'grading_contract_note': (
            'legacy：对全部数值／包含型题目一律要求答案出现文档侧说明，为历史口径；'
            'revised：仅对判据显示涉及文档侧的题目保留该条件，纯数据库单源题按事实正确性计分。'
            '两套口径并列披露，黄金判据文件本身未改动。'),
        'routed_cases': len(routed_rows),
        'routing_accuracy': (sum(row['route_ok'] for row in routed_rows) / len(routed_rows)
                             if routed_rows else None),
        'routing_llm_fallback_rate': (sum(row['llm_fallback'] for row in routed_rows) / len(routed_rows)
                                      if routed_rows else None),
        'plan_valid_rate': (sum(row['plan_valid'] for row in routed_rows) / len(routed_rows)
                            if routed_rows else None),
        'routing_planning_mean_ms': (round(sum(row['routing_planning_ms'] for row in routed_rows)
                                           / len(routed_rows), 2) if routed_rows else None),
        'live_tool_plan_completion': (sum(row['completed'] for row in execution_rows) / len(execution_rows)
                                      if execution_rows else None),
        'live_citation_structurally_valid_rate': (
            sum(row['citation_structurally_valid'] for row in execution_rows) / len(execution_rows)
            if execution_rows else None),
        'live_answer_present_rate': (sum(row['answer_present'] for row in execution_rows) / len(execution_rows)
                                     if execution_rows else None),
        'live_execution_cases': len(execution_rows),
        'live_execution_status_counts': status_counts,
        'live_execution_note': execution_note,
        'live_latency_note': ('第 1 个执行用例按 cold 记录，BGE-M3 首次加载归入该例；'
                              'live_mean_latency_ms 含冷启动，不作稳定均值，'
                              '稳定口径请用 latency_breakdown.warm。'),
        'live_mean_latency_ms': round(sum(latencies) / len(latencies), 2) if latencies else None,
        'live_p95_latency_ms': (round(latencies[int(.95 * (len(latencies) - 1))], 2)
                                if latencies else None),
        'live_avg_llm_calls': (round(sum(row['llm_calls'] for row in execution_rows)
                                     / len(execution_rows), 2) if execution_rows else None),
        'latency_breakdown': latency_summary,
        'cold_start_latency_ms': latency_summary['cold_start_latency_ms'],
        'warm_mean_latency_ms': latency_summary['warm']['mean_ms'],
        'warm_p50_latency_ms': latency_summary['warm']['p50_ms'],
        'warm_p95_latency_ms': latency_summary['warm']['p95_ms'],
        'routing_rows': routed_rows,
        'execution_rows': execution_rows,
        'live_answer_accuracy': answer_accuracy,
        'live_answer_acceptable_rate': answer_acceptable,
        'live_answer_judged_cases': len(judged_rows),
        'live_answer_verdict_counts': verdict_counts,
        'citation_accuracy': _ratio(sum(item['citation_supported'] is True for item in citation_rows),
                                    len(citation_rows)),
        'citation_judged_cases': len(citation_rows),
        'citation_no_claim_cases': sum(row['citation_judgement']['citation_supported'] == 'no_claim'
                                       for row in execution_rows if 'citation_judgement' in row),
        'answer_faithfulness': _ratio(sum(item['faithful'] is True for item in faithful_rows),
                                     len(faithful_rows)),
        'faithfulness_judged_cases': len(faithful_rows),
        'reject_correctness': _ratio(sum(row['verdict'] == 'correct' for row in reject_rows),
                                     len(reject_rows)),
        'reject_judged_cases': len(reject_rows),
        'metric_scope_note': (
            '引用准确率与答案忠实度由人工确认的判据自动比对得出：'
            '分母只含标注了 expected_citation 的文档事实题（设计 8 题）；'
            '无引用计 no_claim 单列；数据库单源题的 SQL 语义越界检查只写入逐题明细，'
            '用于验证语义约束，不并入指标分母。'),
        'live_answer_accuracy_note': (
            f'对照人工确认的黄金集 {golden_name} 自动判分（契约 {grading_contract}）：'
            + ('correct=答案含黄金事实并说明文档侧；partial=数值/名称正确但文档侧未说明；'
               if grading_contract == 'legacy' else
               'correct=答案含黄金事实，且仅对判据显示涉及文档侧的题目另要求文档侧说明；'
               'partial=数值/名称正确但文档侧未说明；')
            + 'wrong=与黄金事实不符或应拒答而未拒答。accuracy 只计 correct。'
            + (f'（黄金文件加载失败：{golden_error}）' if golden_error else '')),
    }
    result['mode'] = 'live'
    result['api_requests'] = usage.api_requests
    result['api_request_cap'] = max_api_requests
    result['llm_usage'] = usage.to_dict()
    result['truncated'] = truncated
    if not metrics_eligible:
        result['draft_warning'] = (f'{golden_name} 未标记为 human-confirmed；'
                                   '本次结果仅用于调试，不得回填 metrics.json 或写入报告。')
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        help='optional JSON output path; the default only prints to stdout')
    parser.add_argument('--live', action='store_true',
                        help='use real LLM routing and real tools; requires --max-api-requests')
    parser.add_argument('--max-api-requests', type=int, default=0,
                        help='hard cap for live LLM requests; 0 keeps the offline default')
    parser.add_argument('--live-cases', type=int, default=DEFAULT_LIVE_CASES,
                        help=f'number of real execution cases in live mode (default {DEFAULT_LIVE_CASES})')
    parser.add_argument('--golden', type=Path, default=None,
                        help='layered golden set path; a non-human-confirmed set is flagged as draft')
    parser.add_argument('--grading-contract', choices=('legacy', 'revised'), default='legacy',
                        help='answer-grading contract; legacy reproduces historical results')
    return parser


def main(argv=None) -> dict:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.live and args.max_api_requests <= 0:
        parser.error('--live requires --max-api-requests > 0')
    if args.live:
        result = run_live(args.max_api_requests, args.live_cases, args.golden,
                          grading_contract=args.grading_contract)
    else:
        result = run()
        result['mode'] = 'controlled_offline'
        result['api_requests'] = 0
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result['output'] = str(args.output)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in {'routing_rows', 'execution_rows'}},
                     ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    main()

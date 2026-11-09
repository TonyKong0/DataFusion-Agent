"""Offline, source-backed V7 benchmark. No DeepSeek calls are made."""
import argparse
import json
import tempfile
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.multimodal_router import route_multimodal
from app.document.chart.analyzer import extract_charts, query_chart
from app.document.image.image_qa import query_image
from app.document.multi_doc.retriever import retrieve_many
from app.document.table.extractor import extract_tables
from app.document.table.qa import query_table
from app.document.versioning.comparator import compare
from app.evidence.multimodal_conflict import detect_multimodal_conflicts
from app.services import document_service, vector_store

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'backend/tests/fixtures/v7'
RESULT = ROOT / 'docs/evaluation_v7_multimodal_results.json'
REPORT = ROOT / 'docs/evaluation_v7_multimodal.md'
CASES = ROOT / 'backend/tests/cases/v7_multimodal_cases.json'


def build_cases() -> list[dict]:
    cases = []
    for label in ('A', 'B'):
        for number in range(1, 11):
            cases.append({'category': 'multi_document', 'question': f'模块{label}{number:02d}负责什么？',
                          'expected_document': f'report_{label.lower()}.pdf', 'expected_route': 'MULTI_DOCUMENT'})
    for number in range(1, 16):
        cases.append({'category': 'version_compare', 'question': f'第{number}种问法：新版相对旧版修改了哪些内容？',
                      'expected_route': 'VERSION_COMPARE'})
    for year in list(range(2001, 2019)) + [2024, 2025]:
        value = 100 + (year - 2001) * 10 if year <= 2018 else (1000 if year == 2024 else 1200)
        cases.append({'category': 'table', 'question': f'表格中{year}年销售额是多少？',
                      'expected_value': str(value), 'expected_route': 'TABLE'})
    chart_checks = [('最高', '三月最大'), ('最低', '一月最小'),
                    ('增长最快', '二月到三月增长最快'), ('趋势', '总体上升'),
                    ('数据点', '3 个可读数据点')]
    for number in range(15):
        cue, expected = chart_checks[number % len(chart_checks)]
        cases.append({'category': 'chart', 'question': f'问题{number+1}：折线图的{cue}是什么？',
                      'expected_text': expected, 'expected_route': 'CHART'})
    for number in range(15):
        cases.append({'category': 'image', 'question': f'第3页架构图包含哪些模块？（问法{number+1}）',
                      'expected_entities': ['Router', 'Planner', 'RAG'], 'expected_route': 'IMAGE'})
    for number in range(15):
        cases.append({'category': 'cross_modal', 'question': f'正文和表格中的增长率是否一致？（样本{number+1}）',
                      'expected_conflict': True, 'expected_route': 'MULTIMODAL'})
    assert len(cases) == 100
    return cases


def _percentage(value: int, total: int) -> float | None:
    return round(value / total, 4) if total else None


def run(output_dir: Path | None = None) -> dict:
    cases = build_cases()
    cases_path = output_dir / 'v7_multimodal_cases.json' if output_dir else CASES
    result_path = output_dir / 'evaluation_v7_multimodal_results.json' if output_dir else RESULT
    report_path = output_dir / 'evaluation_v7_multimodal.md' if output_dir else REPORT
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    old_doc_dir, old_vector_dir = document_service.DOCUMENT_DIR, vector_store.VECTOR_DIR
    rows = []
    with tempfile.TemporaryDirectory(prefix='v7-eval-') as temporary:
        root = Path(temporary)
        document_service.DOCUMENT_DIR = root / 'documents'
        vector_store.VECTOR_DIR = root / 'vectors'
        try:
            ids = {name: document_service.import_document((FIXTURE / name).read_bytes(), name)['document_id']
                   for name in ('multimodal.pdf', 'policy_v1.pdf', 'policy_v2.pdf', 'report_a.pdf', 'report_b.pdf')}
            for name in ('multimodal.pdf', 'report_a.pdf', 'report_b.pdf'):
                document_service.index_document(ids[name])
            multimodal = ids['multimodal.pdf']
            selected = [ids['report_a.pdf'], ids['report_b.pdf'], multimodal]
            diff = compare(ids['policy_v1.pdf'], ids['policy_v2.pdf'])
            table = extract_tables(multimodal)[0]
            chart = extract_charts(multimodal)[0]
            for index, case in enumerate(cases, 1):
                started = perf_counter()
                actual = None
                source_correct = False
                route_correct = False
                try:
                    category = case['category']
                    route_ids = ([ids['policy_v1.pdf'], ids['policy_v2.pdf']] if category == 'version_compare'
                                 else selected if category == 'multi_document' else [multimodal])
                    route = route_multimodal(case['question'], route_ids)['route']
                    route_correct = route == case['expected_route']
                    if category == 'multi_document':
                        hits = retrieve_many(selected, case['question'], 3)
                        source_correct = bool(hits and hits[0]['filename'] == case['expected_document'])
                        passed = any(hit['filename'] == case['expected_document'] for hit in hits)
                        actual = {'hit_documents': [hit['filename'] for hit in hits]}
                    elif category == 'version_compare':
                        passed = any(item['change_type'] == 'modified' and '500' in item['old'] and '600' in item['new']
                                     for item in diff['changes'])
                        source_correct = passed and all(item['old_source'] or item['new_source'] for item in diff['changes'])
                        actual = {'changes': diff['counts']}
                    elif category == 'table':
                        answer = query_table(multimodal, case['question'])
                        passed = str(answer['value']) == case['expected_value']
                        source_correct = bool(answer['sources'] and answer['sources'][0]['page'] == 1)
                        actual = {'value': answer['value']}
                    elif category == 'chart':
                        answer = query_chart(multimodal, case['question'])
                        passed = case['expected_text'] in answer['answer']
                        source_correct = answer['chart']['page'] == 2
                        actual = {'answer': answer['answer']}
                    elif category == 'image':
                        answer = query_image(multimodal, case['question'])
                        passed = set(case['expected_entities']) <= set(answer['image']['entities'])
                        source_correct = answer['image']['page'] == 3 and answer['image']['image_index'] == 1
                        actual = {'entities': answer['image']['entities']}
                    else:
                        offset = index
                        evidence = [
                            {'evidence_id': f't{index}', 'source_type': 'text', 'source_name': 'report.pdf',
                             'fact_key': '增长率', 'fact_value': 20 + offset, 'content': '', 'provenance': {'page': 1}},
                            {'evidence_id': f'b{index}', 'source_type': 'table', 'source_name': 'report.pdf',
                             'fact_key': '增长率', 'fact_value': 18 + offset, 'content': {}, 'provenance': {'page': 2}},
                        ]
                        conflicts = detect_multimodal_conflicts(evidence)
                        passed = len(conflicts) == 1 and conflicts[0]['resolution'] == 'unresolved'
                        source_correct = passed and len(conflicts[0]['values']) == 2
                        actual = {'conflict_count': len(conflicts)}
                    passed = passed and route_correct
                    error = None
                except Exception as failure:
                    passed, error = False, f'{type(failure).__name__}: {failure}'
                rows.append({'case_id': index, **case, 'passed': bool(passed),
                             'source_correct': bool(source_correct), 'route_correct': bool(route_correct), 'actual': actual,
                             'error': error, 'latency_ms': round((perf_counter() - started) * 1000, 2),
                             'llm_calls': 0})
        finally:
            document_service.DOCUMENT_DIR, vector_store.VECTOR_DIR = old_doc_dir, old_vector_dir
    groups = {category: [row for row in rows if row['category'] == category]
              for category in ('multi_document', 'version_compare', 'table', 'chart', 'image', 'cross_modal')}
    gold = {('modified', '第一章 审核规则'), ('added', '第三章 新流程'), ('deleted', '第二章 旧流程')}
    predicted = {(item['change_type'], item['section']) for item in diff['changes']}
    correct_changes = gold & predicted
    table_rows = {row[0]: row[1] for row in table['rows']}
    table_expected = {str(year): str(100 + (year - 2001) * 10) for year in range(2001, 2019)}
    table_expected.update({'2024': '1000', '2025': '1200'})
    metrics = {
        'multi_document_retrieval_recall': _percentage(sum(row['passed'] for row in groups['multi_document']), 20),
        'multi_document_top1_source_accuracy': _percentage(sum(row['source_correct'] for row in groups['multi_document']), 20),
        'change_detection_precision': _percentage(len(correct_changes), len(predicted)),
        'change_detection_recall': _percentage(len(correct_changes), len(gold)),
        'table_extraction_accuracy': _percentage(sum(table_rows.get(k) == v for k, v in table_expected.items()), 20),
        'table_qa_accuracy': _percentage(sum(row['passed'] for row in groups['table']), 20),
        'chart_type_accuracy': 1.0 if chart['type'] == 'line_chart' else 0.0,
        'chart_qa_accuracy': _percentage(sum(row['passed'] for row in groups['chart']), 15),
        'image_qa_accuracy': _percentage(sum(row['passed'] for row in groups['image']), 15),
        'routing_accuracy': _percentage(sum(row['route_correct'] for row in rows), 100),
        'evidence_source_accuracy': _percentage(sum(row['source_correct'] for row in rows), 100),
        'conflict_detection_accuracy': _percentage(sum(row['passed'] for row in groups['cross_modal']), 15),
        'final_answer_accuracy': None,
    }
    ablations = []
    stages = [('A Text-only', {'multi_document', 'version_compare'}),
              ('B Text+Table', {'multi_document', 'version_compare', 'table'}),
              ('C Text+Table+Chart', {'multi_document', 'version_compare', 'table', 'chart'}),
              ('D Full', set(groups))]
    for name, enabled in stages:
        included = [row for row in rows if row['category'] in enabled]
        ablations.append({'stage': name, 'offline_task_success_rate': _percentage(
            sum(row['passed'] for row in included), 100),
            'source_accuracy': _percentage(sum(row['source_correct'] for row in included), 100),
            'unsupported_claim_rate': None,
            'mean_tool_latency_ms': round(sum(row['latency_ms'] for row in included) / len(included), 2) if included else None,
            'llm_calls': 0, 'scope': '受控离线工具测试；关闭的模态按未覆盖计入 100 题分母'})
    output = {'mode': 'controlled_offline_real_pdf', 'cases': len(rows),
              'api_requests': 0,
              'distribution': {key: len(value) for key, value in groups.items()},
              'distinct_pdf_fixtures': 5, 'distinct_charts': 1, 'distinct_images': 1,
              'metrics': metrics, 'ablations': ablations, 'results': rows,
              'limitations': ['未调用 DeepSeek，不测最终生成答案准确率和无依据断言率',
                              '版本题复用同一对文档；图表题复用同一张图；图片题复用同一张架构图',
                              '跨模态冲突 15 题使用有来源字段的受控结构化证据']}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    output['results_file'] = str(result_path)
    output['cases_file'] = str(cases_path)
    output['report_file'] = str(report_path)
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# V7 多模态受控离线评测', '', '使用 5 份真实生成并解析的 PDF；100 条问题/检查，无 DeepSeek 调用。',
             '这不是未知真实文档的泛化准确率，也不是最终 LLM 回答准确率。', '',
             '## 用例分布', '', *(f'- {name}: {count}' for name, count in output['distribution'].items()),
             '', '## 实测指标', '', *(f'- {key}: {value if value is not None else "未测"}' for key, value in metrics.items()),
             '', '## 消融（同一 100 题分母，关闭的模态按未覆盖计）', '',
             '| 配置 | 离线任务成功率 | 来源准确率 | 平均工具耗时 | LLM 调用 |',
             '| --- | ---: | ---: | ---: | ---: |',
             *(f"| {row['stage']} | {row['offline_task_success_rate']} | {row['source_accuracy']} | {row['mean_tool_latency_ms']} ms | 0 |" for row in ablations),
             '', '## 边界', '', *(f'- {item}' for item in output['limitations']),
             '', f'逐题结果：`{result_path}`；题集：`{cases_path}`。']
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        help='write generated cases and reports here instead of tracked docs files')
    args = parser.parse_args()
    result = run(args.output_dir)
    print(json.dumps({'mode': result['mode'], 'cases': result['cases'],
        'distribution': result['distribution'], 'metrics': result['metrics'],
        'ablations': result['ablations'], 'limitations': result['limitations'],
        'api_requests': 0, 'results_file': result['results_file'],
        'report_file': result['report_file']}, ensure_ascii=False, indent=2))

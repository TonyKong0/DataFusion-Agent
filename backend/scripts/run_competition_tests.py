"""Run the existing regression suite and write honest, inspectable reports."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
REPORTS = ROOT / 'reports'

UNMEASURED = {
    'nl2sql_execution_accuracy': '缺少本轮带标准答案的真实 NL2SQL 执行评测',
    'rag_retrieval_hit_rate': '缺少本轮带标注命中片段的真实 RAG 评测',
    'rag_answer_accuracy': '缺少人工标注的文档答案评测',
    'router_accuracy': '当前 pytest 用例是规则/模拟回归，不等于真实问题分布准确率',
    'plan_completion_rate': '未批量运行真实工具编排任务',
    'citation_accuracy': '已由 docs/metrics.json 的分层黄金集补测（人工确认判据 + 自动比对）；pytest 汇总不重复给出该指标，避免两套口径',
    'average_response_ms': 'pytest 执行时间不等于 HTTP 响应时间',
    'p95_response_ms': '未采集足够的真实 HTTP 请求样本',
    'average_llm_calls': '未对本轮真实请求批量采样',
}


def parse_junit(path: Path) -> dict:
    modules = defaultdict(lambda: {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'duration_ms': 0.0})
    failures = []
    for case in ET.parse(path).getroot().iter('testcase'):
        name = case.get('classname') or 'unknown'
        row = modules[name]
        row['total'] += 1
        row['duration_ms'] += float(case.get('time') or 0) * 1000
        failure = case.find('failure')
        if failure is None:
            failure = case.find('error')
        if failure is not None:
            row['failed'] += 1
            failures.append({'module': name, 'case': case.get('name'),
                             'message': (failure.get('message') or '').splitlines()[0][:500]})
        elif case.find('skipped') is not None:
            row['skipped'] += 1
        else:
            row['passed'] += 1
    rows = []
    for name, row in sorted(modules.items()):
        rows.append({'module': name, **{key: row[key] for key in ('total', 'passed', 'failed', 'skipped')},
                     'average_test_ms': round(row['duration_ms'] / row['total'], 2)})
    return {'modules': rows, 'failures': failures,
            'total': sum(row['total'] for row in rows),
            'passed': sum(row['passed'] for row in rows),
            'failed': sum(row['failed'] for row in rows),
            'skipped': sum(row['skipped'] for row in rows)}


def markdown(summary: dict) -> str:
    counts = summary['tests']
    lines = [
        '# 自动化回归测试报告', '',
        f"运行时间：{summary['generated_at']}（UTC）  ",
        f"Python：{summary['python_version']}  ",
        f"测试命令：`{' '.join(summary['command'])}`  ",
        f"状态：**{summary['status']}**", '',
        f"总计 {counts['total']}，通过 {counts['passed']}，失败 {counts['failed']}，跳过 {counts['skipped']}，通过率 {summary['pass_rate']}%。", '',
        '| 模块 | 总计 | 通过 | 失败 | 跳过 | 平均测试耗时 ms |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for row in summary['modules']:
        lines.append(f"| {row['module']} | {row['total']} | {row['passed']} | {row['failed']} | {row['skipped']} | {row['average_test_ms']} |")
    lines += ['', '## 比赛指标测量状态', '',
              '本入口运行回归测试，**不把单元测试通过率冒充真实问答准确率**。以下指标需另行用标注集和真实请求采样。', '',
              '| 指标 | 当前值 | 原因 |', '| --- | ---: | --- |']
    for key, item in summary['metrics'].items():
        lines.append(f"| {key} | 未测 | {item['reason']} |")
    lines += ['', '## 失败定位', '']
    if summary['failures']:
        lines += [f"- `{item['module']}::{item['case']}`：{item['message']}" for item in summary['failures']]
    else:
        lines.append('无测试用例失败。' if summary['status'] == 'passed' else 'pytest 收集或运行中断；见 `reports/pytest_output.txt`。')
    lines += ['', '原始机器可读结果：`reports/test_summary.json`；pytest 输出：`reports/pytest_output.txt`。', '']
    return '\n'.join(lines)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    junit = REPORTS / 'pytest_junit.xml'
    junit.unlink(missing_ok=True)
    command = [sys.executable, '-m', 'pytest', 'tests', '-q', '--tb=short', f'--junitxml={junit}']
    completed = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, errors='replace', check=False)
    (REPORTS / 'pytest_output.txt').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    tests = parse_junit(junit) if junit.exists() else {'modules': [], 'failures': [], 'total': 0,
                                                        'passed': 0, 'failed': 0, 'skipped': 0}
    total = tests['total']
    summary = {'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'python_version': platform.python_version(), 'command': command,
               'status': 'passed' if completed.returncode == 0 and tests['failed'] == 0 and total else 'failed',
               'exit_code': completed.returncode, 'tests': {key: tests[key] for key in ('total', 'passed', 'failed', 'skipped')},
               'pass_rate': round(tests['passed'] / total * 100, 2) if total else None,
               'modules': tests['modules'], 'failures': tests['failures'],
               'metrics': {key: {'value': None, 'reason': reason} for key, reason in UNMEASURED.items()}}
    (REPORTS / 'test_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (REPORTS / 'test_summary.md').write_text(markdown(summary), encoding='utf-8')
    print(f"{summary['status']}: {tests['passed']}/{total} passed, {tests['failed']} failed, {tests['skipped']} skipped")
    print(f"Reports: {REPORTS / 'test_summary.json'} and {REPORTS / 'test_summary.md'}")
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

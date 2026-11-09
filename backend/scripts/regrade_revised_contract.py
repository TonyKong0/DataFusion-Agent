"""Offline re-grade of the two archived v1.8 live runs under the revised contract.

This script does NOT call any LLM, does not re-execute tools, and does not write
to either source result file.  It re-applies both grading contracts to the
answers that were already recorded, so the legacy numbers stay reproducible and
the contract change is auditable from the stored text alone.

Run (from any directory, with the backend virtualenv interpreter):
    python backend/scripts/regrade_revised_contract.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEMO = BACKEND.parent
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'scripts')]

_spec = importlib.util.spec_from_file_location(
    'evaluate_agent_v5', BACKEND / 'scripts' / 'evaluate_agent_v5.py')
ev5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev5)

GOLDEN = BACKEND / 'tests' / 'golden_answers_v1.8.json'
RUNS = {
    'baseline': DEMO / 'docs' / 'evaluation_agent_v1.8_live.json',
    'after': DEMO / 'docs' / 'evaluation_agent_v1.8_revised_live.json',
}
OUT = DEMO / 'docs' / 'evaluation_agent_revised_contract_regrade.json'


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(verdicts: list[str]) -> dict:
    counts = Counter(verdicts)
    total = len(verdicts)
    return {
        'judged_cases': total,
        'verdict_counts': {key: counts.get(key, 0)
                           for key in ('correct', 'partial', 'wrong')},
        'answer_accuracy': (round(counts.get('correct', 0) / total, 12)
                            if total else None),
        'acceptable_rate': (round((counts.get('correct', 0) + counts.get('partial', 0))
                                  / total, 12) if total else None),
    }


def regrade(run_name: str, path: Path, golden: dict[str, dict]) -> dict:
    data = _load(path)
    judged: list[tuple[dict, dict, str, str]] = []
    for row in data['execution_rows']:
        case = golden.get(row['question'])
        if case is None or row.get('layer') == 'S2-C' or row.get('verdict') is None:
            continue
        answer = row.get('answer') or ''
        legacy = ev5.judge_answer(answer, case, contract='legacy')['verdict']
        revised = ev5.judge_answer(answer, case, contract='revised')['verdict']
        # A stored result must still be reproducible under the legacy contract.
        if legacy != row['verdict']:
            raise AssertionError(
                f'{run_name}: stored verdict {row["verdict"]!r} != legacy {legacy!r} '
                f'for {row["question"]!r}')
        judged.append((row, case, legacy, revised))

    legacy_metrics = _metrics([item[2] for item in judged])
    revised_metrics = _metrics([item[3] for item in judged])
    changes = [
        {'question': row['question'], 'layer': row['layer'],
         'legacy_verdict': old, 'revised_verdict': new,
         'document_side_expected': ev5._document_side_expected(case)}
        for row, case, old, new in judged if old != new
    ]
    regressions = [item for item in changes
                   if {'wrong': 0, 'partial': 1, 'correct': 2}[item['revised_verdict']]
                   < {'wrong': 0, 'partial': 1, 'correct': 2}[item['legacy_verdict']]]
    return {
        'source_file': f'docs/{path.name}',
        'source_sha256': _sha256(path),
        'legacy': legacy_metrics,
        'revised': revised_metrics,
        'verdict_changes': changes,
        'regressions': regressions,
    }


def main() -> int:
    golden_meta = _load(GOLDEN)
    if golden_meta.get('status') != 'human-confirmed':
        raise AssertionError('golden set must remain human-confirmed')
    golden = ev5.load_golden_cases(GOLDEN)
    runs = {name: regrade(name, path, golden) for name, path in RUNS.items()}

    affected = runs['baseline']['verdict_changes']
    if (len(affected) != len(runs['after']['verdict_changes'])
            or any(item['regressions'] for item in runs.values())):
        raise AssertionError('unexpected regrade shape or a regression appeared')
    if any(item['document_side_expected'] for item in affected):
        raise AssertionError('revision must only lift the condition on cases '
                             'whose confirmed criteria have no document side')

    delta_before = (runs['baseline']['revised']['answer_accuracy']
                    - runs['baseline']['legacy']['answer_accuracy'])
    delta_after = (runs['after']['revised']['answer_accuracy']
                   - runs['after']['legacy']['answer_accuracy'])
    summary = {
        'golden_set_cases': len(golden),
        'judged_cases': runs['baseline']['legacy']['judged_cases'],
        'revised_affected_cases': len(affected),
        'legacy_baseline_accuracy': runs['baseline']['legacy']['answer_accuracy'],
        'legacy_after_accuracy': runs['after']['legacy']['answer_accuracy'],
        'revised_baseline_accuracy': runs['baseline']['revised']['answer_accuracy'],
        'revised_after_accuracy': runs['after']['revised']['answer_accuracy'],
        'revised_baseline_correct_cases': runs['baseline']['revised']['verdict_counts']['correct'],
        'revised_after_correct_cases': runs['after']['revised']['verdict_counts']['correct'],
        'contract_delta_baseline': round(delta_before, 12),
        'contract_delta_after': round(delta_after, 12),
        'delta_is_constant': abs(delta_before - delta_after) < 1e-9,
        'acceptable_rate_unchanged': (
            runs['baseline']['legacy']['acceptable_rate']
            == runs['baseline']['revised']['acceptable_rate']
            == runs['after']['legacy']['acceptable_rate']
            == runs['after']['revised']['acceptable_rate']),
    }

    payload = {
        'scope': ('对两份已归档的 30 题真实执行结果离线重判，检验修订判分口径的影响；'
                  '未重跑 LLM、未重执行工具、未修改黄金判据、未覆盖任何原始结果文件。'),
        'generated_by': 'backend/scripts/regrade_revised_contract.py',
        'grading_contract': {
            'legacy': ('对全部 numeric / contains 型题目一律要求答案出现文档侧说明'
                       '（含「文档／材料」与「未／无／不」）才计 correct，为历史口径。'),
            'revised': ('仅当人工确认判据显示题目涉及文档侧（target_document、'
                        'expected_citation，或题面含文档／材料）时保留该条件；'
                        '纯数据库单源题按黄金事实正确性计 correct。'),
            'rule_source': 'backend/scripts/evaluate_agent_v5.py::_document_side_expected',
            'unchanged': ['黄金判据文件', '数值容差', '名称包含判据', '拒答／澄清判据',
                          '26 题分母', '引用／忠实度判分', '两份原始结果文件'],
            'disclosure': ('两套口径并列披露，原口径数值不替换、不删除；'
                           '修订口径作用于两次重跑的幅度相同，不构成系统能力提升证据。'),
        },
        'golden_set': {'file': 'backend/tests/golden_answers_v1.8.json',
                       'status': golden_meta['status'],
                       'cases': len(golden)},
        'runs': runs,
        'summary': summary,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'written: {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

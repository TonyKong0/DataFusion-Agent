"""Report-number checker: every traced number must resolve to metrics.json."""

import json

from scripts import check_report_numbers as checker


def _payload():
    return {'metrics': [
        {'id': 'a', 'value': 0.76, 'unit': 'ratio', 'status': 'measured'},
        {'id': 'b', 'value': 7522.5, 'unit': 'ms', 'status': 'measured'},
        {'id': 'c', 'value': 21824, 'unit': 'tokens', 'status': 'measured'},
        {'id': 'd', 'value': None, 'unit': 'ratio', 'status': 'unmeasured'},
    ]}


def test_truth_variants_include_ratio_percentage_and_skip_unmeasured():
    variants = checker.truth_variants(_payload())

    assert 0.76 in variants
    assert 76.0 in variants
    assert 7522.5 in variants
    assert 21824.0 in variants
    assert len(variants) == 4


def test_traceable_numbers_produce_no_findings():
    text = ('多表严格行比对为 76%，平均耗时 7,522.5 ms，'
            '消耗 21824 tokens，稳定版口径 0.76 与实验分支分开。')

    assert checker.scan_text(text, checker.truth_variants(_payload())) == []


def test_invented_percentage_is_reported():
    text = '本轮准确率达到 42%。'

    findings = checker.scan_text(text, checker.truth_variants(_payload()))

    assert len(findings) == 1
    assert findings[0]['token'] == '42%'
    assert findings[0]['context'] == text


def test_placeholders_and_standard_numbers_are_ignored():
    text = ('[待 11-09 从 metrics.json 落位]\n'
            '按 GB/T 7714—2015 顺序编码制著录。\n'
            '版本 v1.7.0，2026 年 11 月。\n'
            '0 引言')

    assert checker.scan_text(text, checker.truth_variants(_payload())) == []


def test_ratio_percentage_matches_repeating_decimal():
    payload = {'metrics': [{'id': 'a', 'value': 0.9166666666666666,
                            'unit': 'ratio', 'status': 'measured'}]}

    assert checker.scan_text('可接受率 91.67%。', checker.truth_variants(payload)) == []


def test_check_reports_file_and_line_for_unmatched(tmp_path):
    draft = tmp_path / 'draft.md'
    draft.write_text('0 引言\n本轮准确率 42%，耗时 999 ms。\n', encoding='utf-8')

    _, unmatched = checker.check([draft], _payload())

    assert {item['token'] for item in unmatched} == {'42%', '999 ms'}
    assert all(item['file'] == str(draft) for item in unmatched)
    assert all(item['line'] == 2 for item in unmatched)


def test_check_passes_on_a_clean_draft(tmp_path):
    draft = tmp_path / 'draft.md'
    draft.write_text('严格行比对 76%，平均耗时 7522.5 ms。\n', encoding='utf-8')

    _, unmatched = checker.check([draft], _payload())

    assert unmatched == []


def test_real_truth_table_is_loadable_and_has_measured_values():
    payload = json.loads(checker.METRICS_PATH.read_text(encoding='utf-8'))

    variants = checker.truth_variants(payload)

    assert 0.76 in variants
    assert 0.8679 in variants
    assert 1.0 in variants

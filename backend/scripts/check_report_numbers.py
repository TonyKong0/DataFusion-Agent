"""Check report drafts against the single source of truth: docs/metrics.json.

This is intentionally a *checker*, not a document generator.  It scans the
high-risk numeric shapes (percentages, milliseconds, token counts, bare
ratios) in a draft, and reports any value that cannot be traced back to a
measured entry in the truth table.  Placeholders, years, version strings and
section numbers are ignored.

Exit code 0 = every checked number is traceable; 1 = unmatched values found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = REPO_ROOT / 'docs' / 'metrics.json'

PERCENT = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*[%％]')
MILLISECONDS = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(?:ms|毫秒)', re.IGNORECASE)
TOKENS = re.compile(r'(\d[\d,]*)\s*(?:tokens?|个\s*token)', re.IGNORECASE)
BARE_RATIO = re.compile(r'(?<![\d.])(0\.\d{2,})(?![\d.])')
SKIP_LINE = re.compile(r'\[待|TODO|占位|GB/T|v1\.\d|https?://|^\s*\|?\s*\d+\s*[.、]')
YEAR = re.compile(r'^(19|20)\d{2}$')


def truth_variants(metrics_payload: dict) -> set[float]:
    """All numeric spellings that a measured metric may legitimately take."""
    variants: set[float] = set()
    for metric in metrics_payload.get('metrics', []):
        if metric.get('status') != 'measured':
            continue
        value = metric.get('value')
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        variants.add(round(float(value), 6))
        if metric.get('unit') == 'ratio':
            variants.add(round(float(value) * 100, 4))
    return variants


def _matches(value: float, kind: str, variants: set[float]) -> bool:
    candidates = [value]
    if kind == 'percent':
        candidates.append(value / 100)
    return any(abs(candidate - known) <= (0.02 if kind == 'percent' else 0.011)
               for candidate in candidates for known in variants)


def scan_text(text: str, variants: set[float]) -> list[dict]:
    findings = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if SKIP_LINE.search(line):
            continue
        spans = [(PERCENT, 'percent'), (MILLISECONDS, 'ms'),
                 (TOKENS, 'tokens'), (BARE_RATIO, 'ratio')]
        for pattern, kind in spans:
            for match in pattern.finditer(line):
                raw = match.group(1).replace(',', '')
                if YEAR.match(raw):
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if not _matches(value, kind, variants):
                    findings.append({'line': line_number, 'token': match.group(0).strip(),
                                     'value': value, 'kind': kind,
                                     'context': line.strip()[:140]})
    return findings


def check(paths: list[Path], metrics_payload: dict | None = None) -> tuple[int, list[dict]]:
    payload = metrics_payload or json.loads(METRICS_PATH.read_text(encoding='utf-8'))
    variants = truth_variants(payload)
    unmatched = []
    checked = 0
    for path in paths:
        text = path.read_text(encoding='utf-8')
        findings = scan_text(text, variants)
        checked += len(text.splitlines())
        for finding in findings:
            unmatched.append({'file': str(path), **finding})
    return checked, unmatched


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('drafts', nargs='+', type=Path, help='report draft files (.md/.html)')
    parser.add_argument('--json', action='store_true', help='emit the unmatched list as JSON')
    args = parser.parse_args(argv)
    _, unmatched = check(args.drafts)
    if args.json:
        print(json.dumps(unmatched, ensure_ascii=False, indent=2))
    elif unmatched:
        for item in unmatched:
            print(f"UNMATCHED {item['file']}:{item['line']} {item['token']} -> {item['context']}")
        print(f'\n{len(unmatched)} untraceable number(s); 见 docs/metrics.json')
    else:
        print(f'OK: {len(args.drafts)} draft(s) checked, 0 untraceable numbers')
    return 1 if unmatched else 0


if __name__ == '__main__':
    sys.exit(main())

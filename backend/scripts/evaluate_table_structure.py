"""Measure the scanned-table pipeline on rasterized fixtures with known ground truth.

Each fixture is rendered to a text-free image page (so the native table finder has
nothing to work with), OCR'd, rebuilt into a grid and compared cell by cell with
the known layout. The layouts are synthetic and clean: this measures the
reconstruction step, not robustness to skew, noise or merged cells.
"""
import argparse
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.document.table.structure import page_image, page_labels, restore_table

FIXTURES = [
    {'name': 'three_by_three',
     'headers': ['Year', 'Revenue', 'Profit'],
     'rows': [['2023', '120', '15'], ['2024', '150', '18']]},
    {'name': 'five_rows_four_columns',
     'headers': ['Region', 'Q1', 'Q2', 'Q3'],
     'rows': [['North', '10', '12', '14'], ['South', '9', '11', '13'],
              ['East', '8', '10', '12'], ['West', '7', '9', '11']]},
    {'name': 'mixed_text_and_numbers',
     'headers': ['Item', 'Count', 'Unit Price'],
     'rows': [['Widget', '5', '19.9'], ['Gadget', '12', '4.5'], ['Cable', '40', '1.2']]},
    # Negative control: cells that are genuinely blank must stay blank. Without
    # this fixture the recovery pass could improve the score by inventing text.
    {'name': 'sparse_with_blank_cells',
     'headers': ['Item', 'Q1', 'Q2'],
     'rows': [['Alpha', '10', ''], ['Beta', '', '20'], ['Gamma', '30', '40']]},
]


def render_image_page(spec: dict):
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    for row_index, row in enumerate([spec['headers'], *spec['rows']]):
        for column_index, cell in enumerate(row):
            if not cell:
                continue
            page.insert_text((60 + column_index * 150, 110 + row_index * 46),
                             cell, fontsize=14)
    pixmap = page.get_pixmap(dpi=150, alpha=False)
    document.close()
    image = pymupdf.open(stream=pixmap.tobytes('png'), filetype='png')
    return image[0]


def evaluate(*, recovery: bool = True) -> dict:
    results = []
    for spec in FIXTURES:
        page = render_image_page(spec)
        image = page_image(page) if recovery else None
        labels = page_labels(page)
        table = restore_table(labels, image=image, page=1, index=1, filename=spec['name'])
        expected = [spec['headers'], *spec['rows']]
        actual = ([table['headers'], *table['rows']] if table else [])
        matched = sum(1 for row_index, row in enumerate(expected)
                      for column_index, value in enumerate(row)
                      if row_index < len(actual) and column_index < len(actual[row_index])
                      and actual[row_index][column_index].replace(' ', '') == value.replace(' ', ''))
        total = sum(len(row) for row in expected)
        results.append({
            'fixture': spec['name'],
            'expected_rows': len(expected), 'expected_columns': len(spec['headers']),
            'restored': table is not None,
            'restored_rows': (table['row_count'] + 1) if table else 0,
            'restored_columns': table['column_count'] if table else 0,
            'cells_expected': total, 'cells_matched': matched,
            'cell_accuracy': round(matched / total, 4) if total else 0.0,
            'exact_table_match': actual == expected,
            'mean_confidence': table['mean_confidence'] if table else None,
            'low_confidence_cells': table['low_confidence_cells'] if table else None,
            'recovered_cells': table['recovered_cells'] if table else 0,
            'recovery_details': table['recovery_details'] if table else [],
            'markdown': table['markdown'] if table else None,
        })
    cells_expected = sum(item['cells_expected'] for item in results)
    cells_matched = sum(item['cells_matched'] for item in results)
    return {'mode': 'rendered_fixtures_real_ocr',
            'scope': ('rasterized text-free pages with clean synthetic layouts; no skew, noise or '
                      'merged cells. Includes a blank-cell negative control.'),
            'recovery_enabled': recovery,
            'fixtures': len(results),
            'recovered_cells': sum(item['recovered_cells'] for item in results),
            'cell_accuracy': round(cells_matched / cells_expected, 4) if cells_expected else 0.0,
            'exact_table_match_rate': round(sum(item['exact_table_match'] for item in results)
                                            / len(results), 4),
            'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='optional JSON output path')
    parser.add_argument('--no-recovery', action='store_true',
                        help='disable empty-cell re-recognition to measure the baseline')
    args = parser.parse_args()
    result = evaluate(recovery=not args.no_recovery)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        result['output'] = str(args.output)
    print(json.dumps({key: value for key, value in result.items() if key != 'results'},
                     ensure_ascii=False, indent=2))

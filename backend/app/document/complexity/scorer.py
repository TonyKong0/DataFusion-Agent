from app.document.complexity.features import extract_features
from app.document.complexity.models import ComplexityResult
from pathlib import Path
import yaml

RULES = yaml.safe_load((Path(__file__).with_name('rules.yaml')).read_text(encoding='utf-8'))


def score_complexity(inspections: list[dict]) -> dict:
    f = extract_features(inspections)
    score = round(100 * (min(f['pages'] / 50, 1) * RULES['page_weight'] +
                  f['scan_ratio'] * RULES['scan_weight'] +
                  min(f['image_count'] / 20, 1) * RULES['image_weight'] +
                  min(f['formula_count'] / 8, 1) * RULES['formula_weight'] +
                  min(f['heading_depth_estimate'] / 3, 1) * RULES['heading_weight'] +
                  f['layout_variation'] * RULES['layout_weight']))
    level = 'Low' if score <= 30 else 'Medium' if score <= 60 else 'High' if score <= 80 else 'Very High'
    factors = []
    if f['scan_ratio']:
        factors.append('扫描页比例较高')
    if f['formula_count']:
        factors.append('包含公式')
    if f['heading_depth_estimate'] >= 2 or f['heading_count'] >= 2:
        factors.append('标题层级较复杂')
    if f['layout_variation'] >= .5:
        factors.append('页面版式变化明显')
    strategy = ['native_parser']
    if f['scan_ratio']:
        strategy.append('enable_ocr')
    if f['formula_count']:
        strategy.append('enable_formula_parser')
    if score >= 31 or f['heading_count'] >= 2:
        strategy.append('hierarchical_chunking')
    return ComplexityResult(score, level, factors, strategy, f).to_dict()

from app.core.errors import AppError
from app.document.formula.formula_parser import parse_formula
from app.document.formula.expression_validator import evaluate_expression
from app.document.formula.unit_normalizer import normalize_value


def calculate_formula(formula, binding: dict) -> dict:
    parsed = parse_formula(formula)
    values = {}
    evidence = []
    kinds = set()
    for safe_name, variable in parsed['variables'].items():
        item = binding.get(variable, {})
        if item.get('status') != 'bound':
            raise AppError('FORMULA_PARAMETER_UNCERTAIN', f'参数“{variable}”缺失或有歧义', 422)
        parameter = item['parameter']
        normalized, kind = normalize_value(parameter['normalized_value'], parameter['unit'])
        values[safe_name] = normalized
        kinds.add(kind)
        evidence.append(parameter)
    if len(kinds - {'number'}) > 1:
        raise AppError('FORMULA_UNIT_CONFLICT', '参数单位类型不兼容', 422)
    result = evaluate_expression(parsed['expression'], values)
    return {'formula_id': formula.formula_id, 'page': formula.page, 'raw_text': formula.raw_text,
            'expression': parsed['expression'], 'variables': values, 'parameters': evidence,
            'result': result, 'unit': parsed['unit'], 'heading_path': formula.heading_path}

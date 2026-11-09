import re
from app.core.errors import AppError


def parse_formula(formula) -> dict:
    if '=' not in formula.raw_text and '＝' not in formula.raw_text:
        raise AppError('FORMULA_PARSE_FAILED', '公式缺少等号', 422)
    left, expression = re.split(r'[=＝]', formula.raw_text, maxsplit=1)
    expression = expression.strip().replace('×', '*').replace('÷', '/').replace('−', '-')
    percent = expression.endswith('%')
    if percent:
        expression = expression[:-1].rstrip()
    names = {}
    for index, variable in enumerate(sorted(formula.variables, key=len, reverse=True)):
        safe_name = f'v{index}'
        expression = re.sub(re.escape(variable), safe_name, expression)
        names[safe_name] = variable
    if re.search(r'[^\d\s.v+\-*/()]', expression):
        raise AppError('FORMULA_PARSE_FAILED', '公式包含不支持的字符', 422)
    return {'name': left.strip(), 'expression': expression, 'variables': names,
            'unit': '%' if percent else ''}

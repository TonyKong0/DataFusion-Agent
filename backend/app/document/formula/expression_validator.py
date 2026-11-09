import ast
import math
from app.core.errors import AppError


def evaluate_expression(expression: str, values: dict[str, float]) -> float:
    if len(expression) > 300 or len(values) > 20:
        raise AppError('FORMULA_UNSAFE', '公式过长', 422)
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError:
        raise AppError('FORMULA_PARSE_FAILED', '公式语法错误', 422) from None
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise AppError('FORMULA_UNSAFE', '公式过于复杂', 422)

    def walk(node, depth=0):
        if depth > 16:
            raise AppError('FORMULA_UNSAFE', '公式嵌套过深', 422)
        if isinstance(node, ast.Expression):
            return walk(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (float, int):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in values:
            return float(values[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand, depth + 1)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = walk(node.left, depth + 1), walk(node.right, depth + 1)
            if isinstance(node.op, ast.Div) and right == 0:
                raise AppError('FORMULA_DIV_ZERO', '公式除数为零', 422)
            result = (left + right if isinstance(node.op, ast.Add) else
                      left - right if isinstance(node.op, ast.Sub) else
                      left * right if isinstance(node.op, ast.Mult) else left / right)
            if not math.isfinite(result) or abs(result) > 1e18:
                raise AppError('FORMULA_UNSAFE', '公式结果超出安全范围', 422)
            return result
        raise AppError('FORMULA_UNSAFE', '公式包含不允许的运算', 422)

    return round(walk(tree), 10)

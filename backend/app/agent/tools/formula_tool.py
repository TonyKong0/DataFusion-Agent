from app.agent.models import ToolResult
from app.core.errors import AppError
from app.services.document_service import load_document
from app.document.formula.models import FormulaCandidate
from app.document.formula.calculator import calculate_formula
import math


def formula_calculate(question: str, context: dict) -> ToolResult:
    document_id = context.get('document_id')
    formula_id = context.get('formula_id')
    if not document_id or not formula_id:
        raise AppError('FORMULA_SELECTION_REQUIRED', '请指定文档与公式', 422)
    document = load_document(document_id)
    candidates = [item for item in document.get('processing', {}).get('formulas', [])
                  if item.get('formula_id') == formula_id]
    if len(candidates) != 1:
        raise AppError('FORMULA_PARAMETER_UNCERTAIN', '公式不存在或参数无法唯一确定', 422)
    candidate = candidates[0]
    database_result = context.get('database_result')
    if context.get('cross_source'):
        if not database_result or not database_result.get('sql'):
            raise AppError('FORMULA_PARAMETER_UNCERTAIN', '缺少可验证的数据库数值', 422)
        columns = database_result.get('columns') or []
        rows = database_result.get('rows') or []
        if len(rows) != 1 or not all(isinstance(name, str) for name in columns):
            raise AppError('FORMULA_PARAMETER_UNCERTAIN', '公式代入需要数据库返回唯一一行', 422)
        row = rows[0] if isinstance(rows[0], dict) else dict(zip(columns, rows[0]))
        lookup = {name.casefold(): name for name in columns}
        variables = candidate.get('variables') or []
        if not variables or not all(variable.casefold() in lookup for variable in variables):
            raise AppError('FORMULA_PARAMETER_UNCERTAIN', '数据库列名未能逐一对应文档公式变量', 422)
        binding = {}
        for variable in variables:
            value = row[lookup[variable.casefold()]]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise AppError('FORMULA_PARAMETER_UNCERTAIN', '数据库参数不是有效数值', 422)
            binding[variable] = {'status': 'bound', 'parameter': {'name': variable,
                'normalized_value': value, 'unit': '', 'page': None,
                'source_text': database_result['sql'], 'confidence': 1.0}}
        formula = FormulaCandidate(candidate['formula_id'], candidate['page'], candidate['raw_text'],
                                   variables, candidate.get('heading_path', []))
        calculation = calculate_formula(formula, binding)
        parameter_source = 'database'
    else:
        if not candidate.get('calculation'):
            raise AppError('FORMULA_PARAMETER_UNCERTAIN', '文档公式参数无法唯一确定', 422)
        calculation = candidate['calculation']
        parameter_source = 'document'
    page = calculation['page']
    chunks = [item for item in document.get('content', []) if item.get('page') == page
              and calculation.get('raw_text', '').strip() in item.get('text', '')]
    if not chunks:
        raise AppError('FORMULA_SOURCE_MISSING', '公式原文未找到对应索引片段', 409)
    source = chunks[0]
    return ToolResult('formula_calculate', True, data={**calculation, 'parameter_source': parameter_source,
        'database_sql': database_result.get('sql') if parameter_source == 'database' else None,
        'source': {
        'document_id': document_id, 'page': page, 'heading_path': source.get('heading_path', []),
        'chunk_id': source['chunk_id'], 'text': source['text']}})

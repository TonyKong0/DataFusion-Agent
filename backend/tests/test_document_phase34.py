import pytest
from app.core.errors import AppError
from app.document.models import DocumentPage
from app.document.formula.formula_detector import detect_formulas
from app.document.formula.parameter_linker import link_parameters
from app.document.formula.calculator import calculate_formula
from app.document.formula.expression_validator import evaluate_expression


def test_growth_formula_with_units_and_sources():
    page = DocumentPage('d', 8, '增长率=(本期值-上期值)/上期值×100%\n本期值为1200万元\n上期值为1000万元')
    formula = detect_formulas([page])[0]
    result = calculate_formula(formula, link_parameters(formula, [page]))
    assert result['result'] == 20 and result['unit'] == '%'
    assert {p['page'] for p in result['parameters']} == {8}


@pytest.mark.parametrize('expression', ['__import__("os")', 'x.__class__', '2**30', '[1,2]', '1/0'])
def test_reject_unsafe_or_invalid_expression(expression):
    with pytest.raises(AppError):
        evaluate_expression(expression, {})

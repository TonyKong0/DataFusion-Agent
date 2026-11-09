from app.document.models import DocumentPage
from app.document.formula.formula_detector import detect_formulas
from app.document.formula.parameter_linker import link_parameters


def test_formula_parameters_and_provenance():
    page = DocumentPage('d', 8, '增长率=(本期值-上期值)/上期值×100%\n本期值为1200万元\n上期值为1000万元')
    formula = detect_formulas([page])[0]
    assert set(formula.variables) == {'本期值', '上期值'}
    linked = link_parameters(formula, [page])
    assert linked['本期值']['parameter']['normalized_value'] == 1200
    assert linked['上期值']['parameter']['page'] == 8


def test_ambiguous_parameters_are_not_silently_selected():
    page = DocumentPage('d', 1, '差额=本期值-上期值\n本期值为10元\n本期值为20元\n上期值为5元')
    linked = link_parameters(detect_formulas([page])[0], [page])
    assert linked['本期值']['status'] == 'ambiguous'


def test_same_page_table_parameter_precedes_adjacent_page():
    formula_page = DocumentPage('d', 8, '差额=本期值-上期值',
        tables=[{'rows': [['本期值', '1200万元'], ['上期值', '1000万元']]}])
    adjacent = DocumentPage('d', 9, '本期值为900万元\n上期值为800万元')
    linked = link_parameters(detect_formulas([formula_page])[0], [formula_page, adjacent])
    assert linked['本期值']['status'] == 'bound'
    assert linked['本期值']['parameter']['normalized_value'] == 1200

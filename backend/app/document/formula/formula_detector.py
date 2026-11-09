import re
from app.document.formula.models import FormulaCandidate

TOKEN = re.compile(r'[\u4e00-\u9fff]{2,12}|[A-Za-z_][A-Za-z_0-9]*')
STOP = {'SUM', 'AVG', 'MAX', 'MIN', 'ROUND', '增长率', '利润率', '毛利率', '占比', '百分比'}


def detect_formulas(pages: list) -> list[FormulaCandidate]:
    formulas = []
    for page in pages:
        for line in page.text.splitlines():
            line = line.strip()
            if len(line) > 180 or not re.search(r'[=＝]', line):
                continue
            left, right = re.split(r'[=＝]', line, maxsplit=1)
            if not re.search(r'[+\-×*/÷()]', right):
                continue
            variables = list(dict.fromkeys(token for token in TOKEN.findall(right)
                                            if token.upper() not in STOP and not token.isdigit()))
            if not variables:
                continue
            formulas.append(FormulaCandidate(f'formula_{len(formulas)+1:03}', page.page, line, variables))
    return formulas

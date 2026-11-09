import re
from app.document.formula.models import FormulaParameter

NUMBER = r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(亿元|万元|元|%|秒|分钟|KB|MB|GB)?'


def extract_parameters(page_text: str, variable: str, page_number: int,
                       formula_line: str = '', tables: list[dict] | None = None) -> list[FormulaParameter]:
    found = []
    escaped = re.escape(variable)
    pattern = re.compile(escaped + r'\s*(?:为|是|:|：|=|＝)?\s*' + NUMBER, re.I)
    lines = page_text.splitlines()
    for line in lines:
        if line.strip() == formula_line.strip():
            continue
        for match in pattern.finditer(line):
            value = float(match.group(1).replace(',', ''))
            found.append(FormulaParameter(variable, match.group(1), value,
                         match.group(2) or '', page_number, line.strip(), .96))
    for index, line in enumerate(lines[:-1]):
        if line.strip() != variable:
            continue
        match = re.fullmatch(r'\s*' + NUMBER + r'\s*', lines[index+1], re.I)
        if match:
            found.append(FormulaParameter(variable, match.group(1), float(match.group(1).replace(',', '')),
                         match.group(2) or '', page_number, f'{line.strip()} | {lines[index+1].strip()}', .82))
    for table in tables or []:
        for row in table.get('rows', []):
            for index, cell in enumerate(row[:-1]):
                if str(cell or '').strip() != variable:
                    continue
                match = re.fullmatch(r'\s*' + NUMBER + r'\s*', str(row[index+1] or ''), re.I)
                if match:
                    found.append(FormulaParameter(variable, match.group(1), float(match.group(1).replace(',', '')),
                        match.group(2) or '', page_number, ' | '.join(str(value or '') for value in row), .9))
    return found

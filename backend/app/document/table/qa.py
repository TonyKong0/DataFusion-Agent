import re
from app.core.errors import AppError
from app.document.table.extractor import extract_tables
from app.document.table.structure import CELL_CONFIDENCE_WARNING


def _number(value: str) -> float | None:
    match = re.search(r'-?\d+(?:,\d{3})*(?:\.\d+)?', value)
    return float(match.group().replace(',', '')) if match else None


def query_table(document_id: str, question: str) -> dict:
    tables = extract_tables(document_id)
    restored = False
    if not tables:
        # 扫描页没有原生表格结构，退回到 OCR 框的行列重建
        from app.document.table.structure import restore_scanned_tables
        try:
            tables = restore_scanned_tables(document_id)
            restored = bool(tables)
        except AppError:
            tables = []
    years = re.findall(r'20\d{2}', question)
    for table in tables:
        headers = table['headers']
        target_columns = [(i, name) for i, name in enumerate(headers[1:], 1) if name and name in question]
        if not target_columns:
            continue
        col, name = target_columns[0]
        if len(set(years)) >= 2 and ('增长' in question or '变化' in question or '差' in question):
            distinct_years = list(dict.fromkeys(years))[:2]
            matched = [(idx, row) for idx, row in enumerate(table['rows'], 1)
                       if any(year in row[0] for year in distinct_years)]
            if len(matched) == 2 and all(_number(row[col]) is not None for _, row in matched):
                old, new = sorted(matched, key=lambda pair: _number(pair[1][0]) or 0)
                a, b = _number(old[1][col]), _number(new[1][col])
                growth = (b - a) / a * 100 if a else None
                if growth is not None:
                    return {'answer': f'{new[1][0]} 年{name}比 {old[1][0]} 年增长 {growth:g}%（{a:g} → {b:g}）。',
                            'value': growth, 'operation': 'growth_rate', 'sources': [
                                {**table, 'row_index': idx, 'column_index': col, 'row': row}
                                for idx, row in (old, new)]}
        indexed_rows = list(enumerate(table['rows'], 1))
        for index, row in (indexed_rows if years else reversed(indexed_rows)):
            if years and not any(year in row[0] for year in years):
                continue
            if col >= len(row) or row[col].strip() in ('', '-', '—', 'N/A'):
                continue
            result = {'answer': f'{row[0]} 的{name}为 {row[col]}。', 'value': row[col],
                      'operation': 'cell_lookup', 'sources': [{**table, 'row_index': index,
                                                                'column_index': col, 'row': row}]}
            confidences = table.get('cell_confidence') or []
            if (confidences and index < len(confidences) and col < len(confidences[index])
                    and confidences[index][col] < CELL_CONFIDENCE_WARNING):
                result['confidence_warning'] = '该单元格的 OCR 置信度偏低，请对照原页核对'
            return result
    if restored:
        raise AppError('TABLE_ANSWER_UNSUPPORTED',
                       '扫描表格已按 OCR 行列还原，但问题中的年份或列名没有匹配到表头；请改用表头中出现的列名', 422)
    raise AppError('TABLE_ANSWER_UNSUPPORTED', '未找到可核对的表格单元格；请明确年份和列名', 422)

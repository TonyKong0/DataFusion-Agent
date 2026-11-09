import re
import pymupdf
from app.core.errors import AppError
from app.services.document_service import original_pdf_path, load_document

TYPES = {'柱状图': 'bar_chart', '条形图': 'bar_chart', '折线图': 'line_chart', '饼图': 'pie_chart'}
POINT = re.compile(r'^\s*([\w\u4e00-\u9fff]{1,16})\s*[:：\s]\s*(-?\d+(?:\.\d+)?)\s*%?\s*$')


def analyze_chart_text(text: str, page: int, document_id: str, filename: str) -> list[dict]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    charts = []
    for index, line in enumerate(lines):
        kind = next((name for marker, name in TYPES.items() if marker in line), None)
        if not kind:
            continue
        window = lines[index + 1:index + 18]
        points = []
        for candidate in window:
            match = POINT.match(candidate)
            if match:
                points.append({'label': match.group(1), 'value': float(match.group(2)),
                               'source_text': candidate})
        legend = next((row.split('：', 1)[-1].strip() for row in window if row.startswith('图例')), None)
        charts.append({'document_id': document_id, 'filename': filename, 'page': page,
                       'chart_index': len(charts) + 1, 'type': kind, 'title': line,
                       'legend': legend, 'series': points,
                       'confidence': .9 if len(points) >= 2 else .6,
                       'source_text': '\n'.join([line] + window)})
    return charts


def extract_charts(document_id: str) -> list[dict]:
    document = load_document(document_id)
    extension = document.get('extension') or document.get('filename', '').rsplit('.', 1)[-1].lower()
    if extension not in {'pdf', '.pdf'}:
        raise AppError('CHART_NOT_FOUND', '目前只支持 PDF 中带可读文字标签的图表', 422)
    path, _ = original_pdf_path(document_id)
    with pymupdf.open(path) as pdf:
        return [{**chart, 'extension': '.pdf', 'preview_available': True}
                for number, page in enumerate(pdf, 1)
                for chart in analyze_chart_text(page.get_text('text'), number, document_id, document['filename'])]


def query_chart(document_id: str, question: str) -> dict:
    charts = extract_charts(document_id)
    if not charts:
        raise AppError('CHART_NOT_FOUND', '没有找到带可读取标题的柱状图、折线图或饼图', 422)
    chart = next((item for item in charts if any(marker in question and item['type'] == kind
                 for marker, kind in TYPES.items())), charts[0])
    points = chart['series']
    if not points:
        if any(cue in question for cue in ('最大', '最小', '趋势', '增长')):
            raise AppError('CHART_DATA_UNREADABLE', '图表数值标签无法可靠读取，不能推断最大值或趋势', 422)
        answer = f"第 {chart['page']} 页图表标题为“{chart['title']}”。"
    elif '增长最快' in question and len(points) >= 2:
        deltas = [(points[i]['value'] - points[i - 1]['value'], points[i - 1], points[i])
                  for i in range(1, len(points))]
        growth, before, after = max(deltas, key=lambda row: row[0])
        answer = f"{before['label']}到{after['label']}增长最快，增加 {growth:g}。"
    elif '最大' in question or '最高' in question:
        item = max(points, key=lambda row: row['value'])
        answer = f"{item['label']}最大，值为 {item['value']:g}。"
    elif '最小' in question or '最低' in question:
        item = min(points, key=lambda row: row['value'])
        answer = f"{item['label']}最小，值为 {item['value']:g}。"
    elif '趋势' in question and len(points) >= 2:
        change = points[-1]['value'] - points[0]['value']
        direction = '上升' if change > 0 else '下降' if change < 0 else '持平'
        answer = f"从{points[0]['label']}到{points[-1]['label']}总体{direction}（{points[0]['value']:g} → {points[-1]['value']:g}）。"
    else:
        answer = f"第 {chart['page']} 页{chart['title']}包含 {len(points)} 个可读数据点。"
    return {'answer': answer, 'chart': chart, 'sources': [chart]}

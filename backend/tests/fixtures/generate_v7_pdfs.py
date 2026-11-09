"""Generate five small synthetic PDF fixtures for reproducible offline V7 evaluation."""
from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / 'v7'
FONT = Path(r'C:\Windows\Fonts\simhei.ttf')


def page(path, lines):
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.setFont('SimHeiFixture', 15)
    y = 770
    for line in lines:
        c.drawString(48, y, line)
        y -= 38
    c.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('SimHeiFixture', str(FONT)))
    page(OUT / 'policy_v1.pdf', ['第一章 审核规则', '审核阈值为500元。', '第二章 旧流程', '旧流程使用人工复核。'])
    page(OUT / 'policy_v2.pdf', ['第一章 审核规则', '审核阈值为600元。', '第三章 新流程', '新流程使用自动复核。'])
    for label in ('A', 'B'):
        lines = [f'报告{label}系统架构说明'] + [f'模块{label}{i:02d}负责第{i:02d}项任务。' for i in range(1, 11)]
        page(OUT / f'report_{label.lower()}.pdf', lines)

    c = canvas.Canvas(str(OUT / 'multimodal.pdf'), pagesize=(595, 842))
    c.setFont('SimHeiFixture', 18)
    c.drawString(48, 790, '年度销售统计表格')
    c.setFont('SimHeiFixture', 12)
    c.drawString(48, 755, '正文：增长率为20%。')
    rows = [['年份', '销售额', '增长率']]
    rows += [[str(year), str(100 + (year - 2001) * 10), '-'] for year in range(2001, 2019)]
    rows += [['2024', '1000', '-'], ['2025', '1200', '18%']]
    table = Table(rows, colWidths=[140, 140, 140], rowHeights=22)
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, -1), 'SimHeiFixture'), ('FONTSIZE', (0, 0), (-1, -1), 12)]))
    table.wrapOn(c, 500, 500)
    table.drawOn(c, 48, 230)
    c.showPage()
    c.setFont('SimHeiFixture', 18)
    c.drawString(48, 790, '月度增长折线图')
    c.setFont('SimHeiFixture', 12)
    for y, text in [(750, '一月 100'), (720, '二月 120'), (690, '三月 170'), (660, '图例：销量')]:
        c.drawString(48, y, text)
    c.setStrokeColor(colors.darkgreen)
    c.setLineWidth(3)
    c.lines([(80, 430, 230, 465), (230, 465, 390, 570)])
    c.showPage()

    image = Image.new('RGB', (800, 260), '#ffffff')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 36)
    draw.line([(225, 125), (285, 125), (485, 125), (555, 125)], fill='#146947', width=5)
    for x, label in [(25, 'Router'), (285, 'Planner'), (555, 'RAG')]:
        draw.rounded_rectangle((x, 70, x + 200, 185), radius=14, fill='#e0f2e8', outline='#146947', width=4)
        draw.text((x + 20, 105), label, fill='#0f3829', font=font)
    stream = BytesIO()
    image.save(stream, format='PNG')
    c.setFont('SimHeiFixture', 18)
    c.drawString(48, 790, '系统架构图')
    c.drawImage(__import__('reportlab.lib.utils', fromlist=['ImageReader']).ImageReader(BytesIO(stream.getvalue())),
                48, 500, width=500, height=162)
    c.save()
    print('generated', len(list(OUT.glob('*.pdf'))), 'PDF fixtures')


if __name__ == '__main__':
    main()

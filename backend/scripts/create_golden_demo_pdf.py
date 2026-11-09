"""Optional reproducible generator for the competition's synthetic source PDF."""
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'output' / 'pdf' / 'chinook_golden_demo.pdf'
FONT = Path(r'C:\Windows\Fonts\simhei.ttf')


def main():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as error:
        raise SystemExit('缺少 ReportLab；请在 backend 目录安装 `python -m pip install -r requirements-dev.txt`') from error
    if not FONT.is_file():
        raise SystemExit(f'缺少中文字体：{FONT}。请在 Windows 机器安装黑体后重试。')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT,
                        help=f'输出路径（默认：{OUTPUT}）；不会覆盖已有文件')
    output = parser.parse_args().output.resolve()
    if output.exists():
        raise SystemExit(f'输出文件已存在，为避免覆盖而停止：{output}。请另选 --output 路径。')
    output.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('ChineseDemo', str(FONT)))
    page = canvas.Canvas(str(output), pagesize=(595, 842))
    page.setTitle('Chinook 跨源演示资料')
    page.setFillColorRGB(.07, .19, .22)
    page.rect(0, 760, 595, 82, fill=1, stroke=0)
    page.setFillColorRGB(1, 1, 1)
    page.setFont('ChineseDemo', 23)
    page.drawString(48, 793, 'Chinook 跨源演示资料')
    page.setFillColorRGB(.13, .23, .25)
    lines = [
        ('第一章 数据口径', 17),
        ('本文是比赛演示用的合成资料，不代表真实业务规定。', 11),
        ('数据库的订单对应 Chinook 的 Invoice 表；金额沿用数据库示例单位。', 11),
        ('单笔订单金额审核阈值为 5 元。超过阈值指 Invoice.Total > 5。', 11),
        ('第二章 音乐类型说明', 17),
        ('Rock 是本演示资料中的摇滚音乐类型名称。', 11),
        ('若数据库销量最高类型为 Rock，可用该原文核实名称关联。', 11),
        ('第三章 计算示例', 17),
        ('增长率=(本期值-上期值)/上期值×100%', 11),
        ('本期值为120元', 11),
        ('上期值为100元', 11),
        ('示例增长率为20%。', 11),
    ]
    y = 715
    for value, size in lines:
        if size == 17:
            y -= 22
            page.setFillColorRGB(.07, .38, .30)
        else:
            page.setFillColorRGB(.13, .23, .25)
        page.setFont('ChineseDemo', size)
        page.drawString(48, y, value)
        y -= 43 if size == 17 else 35
    page.setStrokeColorRGB(.8, .85, .82)
    page.line(48, 60, 547, 60)
    page.setFont('ChineseDemo', 9)
    page.drawString(48, 42, 'Synthetic competition demo source · Page 1')
    page.save()
    print(output)


if __name__ == '__main__':
    main()

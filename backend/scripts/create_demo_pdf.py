"""Create an original, text-based Chinese fixture with verifiable page facts."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.pagesizes import A4

SECTIONS = [
    ('系统概览', 'DataFusion Agent 基础版提供 Chinook MySQL 单表自然语言问数与单 PDF 资料问答。目标是形成能运行、能演示、能解释、能测试的基础 Demo。系统只展示工具执行记录，不展示模型私有思维链。'),
    ('数据库与 Schema', '数据库使用 MySQL 8 及 Chinook 示例数据。Chinook 有 11 张表。Schema Loader 从 information_schema 实时读取表名、字段类型、主键和外键。艺术家表为 Artist，音乐类型表为 Genre。'),
    ('SQL 安全策略', '所有生成 SQL 必须经过安全校验。只允许单表 SELECT，禁止 JOIN、子查询、INSERT、UPDATE、DELETE、DROP 和危险函数。查询最多返回 100 行，SQL 执行超时为 5 秒。数据库查询使用只读事务。'),
    ('PDF 上传与解析', '基础版一次只维护一份普通文本 PDF。文件大小上限为 20 MB，最多 100 页。使用 PyMuPDF 按页提取文本，保留 document_id、filename 和 page。扫描 PDF、OCR 和加密 PDF 不在支持范围内。'),
    ('文本切片', '文档按页切片，不跨页合并。默认 chunk_size 是 800 个字符，chunk_overlap 是 120 个字符。每个 Chunk 保存 chunk_id、document_id、filename、页码和原始文本，以便追溯答案。'),
    ('向量检索', '基础版使用 BAAI/bge-m3 生成文本 Embedding，并以 FAISS 保存本地向量索引。向量先进行归一化，再通过内积计算余弦相似度。问答默认检索 Top-K 等于 5 的资料片段。'),
    ('答案与引用', 'DeepSeek 只能根据检索到的 Context 回答文档问题。答案引用必须关联实际检索 Chunk，展示来源文件、页码和原始文本。资料未提供的信息，必须回答：根据当前文档无法确定。不得编造电话号码或来源页码。'),
    ('前端交互', '前端基于现有 Vue 3、Vite 和 JavaScript，使用 vue-router。首页路由是 /，核心 Demo 路由是 /data-agent。用户手动切换数据库问数和文档问答，页面展示 SQL、Query Result、Sources 和 Execution Trace。'),
    ('运行配置', '后端为 Python FastAPI，默认端口 8000；Vite 前端开发端口 5173。MySQL 密码和 DeepSeek API Key 只放本地 .env，示例文件 .env.example 不包含真实凭据。日志不记录数据库密码或 API Key。'),
    ('基础验收', '基础 Demo 至少需要 10 个 NL2SQL 用例和 10 个 RAG 用例。NL2SQL 验证表名、SQL 可执行和结果；RAG 验证命中页码、回答关键事实和引用。当前基础范围不实现多表 JOIN、复杂 Agent、OCR 或 Schema Linking。'),
]


def main() -> None:
    output = Path(__file__).resolve().parents[2] / 'docs/demo.pdf'
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    document = canvas.Canvas(str(output), pagesize=A4)
    document.setTitle('DataFusion Agent 基础版演示资料')
    width, height = A4
    for index, (title, text) in enumerate(SECTIONS, 1):
        document.setFillColorRGB(.12, .24, .43)
        document.setFont('STSong-Light', 22)
        document.drawString(48, height-70, f'{index:02}  {title}')
        document.setFont('STSong-Light', 11)
        document.setFillColorRGB(.2, .25, .32)
        lines = [text[i:i+36] for i in range(0, len(text), 36)]
        for line_index, line in enumerate(lines):
            document.drawString(48, height-125-line_index*24, line)
        document.setFillColorRGB(.4, .45, .5)
        document.setFont('STSong-Light', 10)
        document.drawString(48, 52, 'DataFusion Agent | 原创测试资料 | 基础 Demo')
        document.drawRightString(width-48, 52, f'Page {index} / {len(SECTIONS)}')
        document.showPage()
    document.save()
    print('Created docs/demo.pdf: 10 pages')


if __name__ == '__main__':
    main()

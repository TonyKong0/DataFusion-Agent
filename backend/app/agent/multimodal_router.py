"""Deterministic routing for material tools and optional database evidence."""
from app.core.errors import AppError

MATERIAL_CUES = ('材料', '文档', 'PDF', 'pdf', '资料', '报告', '手册', '原文', '文件', '知识库')
DATABASE_CUES = ('数据库', 'SQL', 'Chinook', 'MySQL')


def route_multimodal(question: str, document_ids: list[str]) -> dict:
    docs = list(dict.fromkeys(document_ids))
    if len(docs) > 10:
        raise AppError('TOO_MANY_DOCUMENTS', '每轮最多选择 10 份材料', 422)
    compare = any(word in question for word in ('版本', '新版', '旧版', '修改了', '变化了', '差异'))
    chart = any(word in question for word in ('折线图', '柱状图', '条形图', '饼图', '图表'))
    image = any(word in question for word in ('架构图', '流程图', '示意图', '插图', '截图', '图片'))
    table = any(word in question for word in ('表格', '表中', '表内')) or (
        len(docs) == 1 and question.count('20') >= 2 and any(word in question for word in ('销售额', '增长率')))
    database = any(word.lower() in question.lower() for word in DATABASE_CUES)
    material_mentioned = any(word.lower() in question.lower() for word in MATERIAL_CUES)
    material_requested = bool(docs) and (not database or material_mentioned or compare or chart or image or table)
    if not docs and not database:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '请先选择已索引材料', 422)
    if compare and material_requested and len(docs) != 2:
        raise AppError('DOCUMENT_SELECTION_REQUIRED', '版本对比请选择旧版和新版两份材料', 422)

    tools = []
    if material_requested:
        if compare:
            tools.append('document_compare')
        if chart:
            tools.append('chart_analyze')
        if image:
            tools.append('image_query')
        if table and any(word in question for word in ('正文', '原文')):
            tools.append('document_search')
        if table:
            tools.append('table_query')
        if not tools:
            tools.append('multi_document_search' if len(docs) >= 2 else 'document_search')
    if database:
        tools.append('database_query')

    if database and material_requested:
        route = 'CROSS_SOURCE'
    elif tools:
        route = ('VERSION_COMPARE' if compare else 'MULTI_DOCUMENT' if len(docs) >= 2 and tools == ['multi_document_search']
                 else 'MULTIMODAL' if len(tools) > 1 else
                 'CHART' if chart else 'IMAGE' if image else 'TABLE' if table else 'DOCUMENT_ONLY')
    else:
        route = 'DATABASE_ONLY'
    return {'route': route, 'required_tools': tools or ['database_query'],
            'reason': ['按问题中的材料模态与数据源线索选择工具'], 'document_ids': docs}

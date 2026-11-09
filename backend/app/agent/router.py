"""Rule and semantic-element routing; bounded structured LLM fallback only if ambiguous."""
import json
import re
from app.core.errors import AppError
from app.llm.deepseek_client import chat_json
from app.semantic.normalizer import normalize_question
from app.semantic.element_extractor import extract_rule_elements
from app.agent.material_reference import SELECTED_MATERIAL_REFERENCE

ROUTES = {'DATABASE_ONLY', 'DOCUMENT_ONLY', 'CROSS_SOURCE', 'CLARIFICATION_REQUIRED'}
DOCUMENT_CUES = ('文档', 'PDF', 'pdf', '手册', '资料', '材料', '文章', '课件', '报告', '原文', '说明书', '知识库',
                 '章节', '第1章', '第2章', '公式', '作者', '出处')
DATABASE_CUES = ('数据库', 'Chinook', 'SQL', '客户', '顾客', '订单', '发票', '歌曲', '曲目',
                 '音乐类型', '流派', '曲风', '艺术家', '歌手', '专辑', '员工', '销售额', '销量', '购买')
DATABASE_SOURCE_CUES = ('数据库', 'Chinook', 'MySQL', 'SQL')
DATABASE_ACTION_CUES = ('查出', '查询', '统计', '多少', '数量', '总额', '最多', '最高', '最贵',
                        '最低', '最便宜', '相差', '符合', '计算', '有几', '查一下', '对比',
                        '比较', '差异', '是否一致', '一致吗', '相同吗', '有何不同')
FALLBACK_SYSTEM = ('对问题分类，只输出 JSON：{"route":"DATABASE_ONLY|DOCUMENT_ONLY|CROSS_SOURCE|CLARIFICATION_REQUIRED",'
                   '"confidence":0.0}。只使用问题中显式的数据源线索，不猜测未提供的文档或数据库。')


def route_query(question: str, *, allow_llm: bool = True,
                selected_document_count: int = 0) -> dict:
    normalized = normalize_question(question)['normalized_question']
    elements = [item.to_dict() for item in extract_rule_elements(question, normalized)]
    selected_reference = (SELECTED_MATERIAL_REFERENCE.search(question)
                          if selected_document_count else None)
    document = bool(selected_reference) or any(cue.lower() in question.lower() for cue in DOCUMENT_CUES) or bool(
        re.search(r'第[一二三四五六七八九十\d]+章', question))
    document_position = min((question.lower().find(cue.lower()) for cue in DOCUMENT_CUES
                            if cue.lower() in question.lower()), default=len(question))
    if selected_reference:
        document_position = min(document_position, selected_reference.start())
    database_source = any(cue.lower() in question.lower() for cue in DATABASE_SOURCE_CUES)
    database_cues = [cue for cue in DATABASE_CUES if cue.lower() in question.lower()]
    database_position = min((question.lower().find(cue.lower()) for cue in database_cues),
                            default=len(question))
    database = database_source or bool(database_cues) or any(
        item['type'] == 'entity' for item in elements)
    reasons = []
    if database:
        reasons.append('存在数据库实体或统计线索')
    if document:
        reasons.append('存在文档、章节或公式线索')
    database_action = any(cue in question for cue in DATABASE_ACTION_CUES)
    document_criteria_for_database = bool(re.search(
        r'(?:用|按|根据|按照|依据|依照|参照).{0,24}(?:文档|PDF|手册|资料|报告|说明书).{0,32}'
        r'(?:检查|核对|验证|筛选|判断|过滤).{0,24}(?:数据库|Chinook|MySQL|SQL)',
        question,
    ))
    database_action = database_action or document_criteria_for_database
    if database_source and document and database_action:
        route, confidence = 'CROSS_SOURCE', .94
    elif (database and document and database_position < document_position and database_action):
        route, confidence = 'CROSS_SOURCE', .94
    elif document:
        # A domain term such as “订单” can appear inside a document-only
        # policy question; it does not request a database lookup by itself.
        route, confidence = 'DOCUMENT_ONLY', .95
    elif database:
        route, confidence = 'DATABASE_ONLY', .95
    else:
        route, confidence = 'CLARIFICATION_REQUIRED', .4
        if allow_llm:
            try:
                output = chat_json(FALLBACK_SYSTEM, json.dumps(
                    {'question': question, 'normalized_question': normalized, 'elements': elements}, ensure_ascii=False))
                proposed = output.get('route')
                score = output.get('confidence')
                if proposed in ROUTES and isinstance(score, (int, float)) and .65 <= score <= 1:
                    route, confidence = proposed, min(float(score), .8)
                    reasons.append('结构化模型分类')
            except AppError:
                pass
    required = (['database_query', 'document_search'] if route == 'CROSS_SOURCE' else
                ['database_query'] if route == 'DATABASE_ONLY' else
                ['document_search'] if route == 'DOCUMENT_ONLY' else ['clarification'])
    if route == 'CROSS_SOURCE' and '公式' in question:
        required.append('formula_calculate')
    return {'route': route, 'required_tools': required, 'reason': reasons or ['数据源不明确'],
            'confidence': confidence, 'normalized_question': normalized, 'elements': elements}

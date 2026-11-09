import pytest
from app.agent.router import route_query

DATABASE = [
    '美国客户有多少？', '列出所有音乐类型', '销量最高的歌曲是什么？', '每个客户消费了多少钱？',
    '数据库中有多少订单？', '哪个艺术家的专辑最多？', 'Chinook 中有几位员工？',
    '查询价格最高的10首歌曲', '哪个流派卖得最多？', '显示客户名单',
]
DOCUMENT = [
    '这份文档主要讲什么？', 'PDF 第2章介绍了什么？', '手册中如何定义缓存？',
    '报告的作者是谁？', '资料里有什么公式？', '说明书的注意事项是什么？',
    '请总结原文第三章', '文档中的增长率怎么算？', '知识库对流程有什么描述？',
    '请找出 PDF 的结论',
]
CROSS = [
    '数据库中销量最高的音乐类型，在文档中有什么说明？',
    '文档规定审核阈值是多少，数据库里多少订单超过它？',
    '数据库客户数与报告中的客户数是否一致？',
    '查出最贵的歌曲，PDF 中如何描述它？',
    '文档中的销售目标与数据库销售额相差多少？',
    '手册中对订单的规定，数据库有多少订单符合？',
    '数据库中艺术家最多的类型，说明书怎么解释？',
    '报告说今年销量是多少，数据库实际销量是多少？',
    '根据文档里的公式计算数据库销售额增长率',
    '数据库里员工人数和文档描述一致吗？',
    'PDF 说客户来自哪些国家，数据库各国客户数是多少？',
    '数据库里销量最高的专辑，在文档中有何特点？',
    '文档定义了哪种流派，数据库中这种流派有几首歌曲？',
    '数据库订单总额是否超过报告给出的预算？',
    '用手册里的标准检查数据库客户记录',
]
CLARIFY = ['它是什么？', '给我看看', '分析一下', '有什么变化？', '请回答这个问题']


@pytest.mark.parametrize('question,expected',
    [(q, 'DATABASE_ONLY') for q in DATABASE] +
    [(q, 'DOCUMENT_ONLY') for q in DOCUMENT] +
    [(q, 'CROSS_SOURCE') for q in CROSS] +
    [(q, 'CLARIFICATION_REQUIRED') for q in CLARIFY])
def test_router_40_cases(question, expected):
    assert route_query(question, allow_llm=False)['route'] == expected

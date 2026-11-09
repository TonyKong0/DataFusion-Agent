export const routeLabels = {
  DATABASE_ONLY: '数据库查询',
  DOCUMENT_ONLY: '材料问答',
  CROSS_SOURCE: '跨源综合',
  CLARIFICATION_REQUIRED: '需要补充信息',
  MULTI_DOCUMENT: '多材料检索',
  MULTIMODAL: '材料多模态分析',
  VERSION_COMPARE: '材料版本对比',
  CHART: '图表分析',
  IMAGE: '图片文字识别',
  TABLE: '表格查询',
}

export const toolLabels = {
  database_query: '查询数据库',
  document_search: '材料检索与回答',
  formula_calculate: '计算材料公式',
  clarification: '澄清问题',
  multi_document_search: '联合检索多份材料',
  document_compare: '比较材料版本',
  table_query: '查询材料表格',
  chart_analyze: '分析材料图表',
  image_query: '识别图片文字',
}

export const statusLabels = {
  success: '已完成',
  partial_success: '部分完成',
  need_clarification: '需要补充信息',
  failed: '未完成',
  missing_dependency: '缺少前一步结果',
  timeout: '执行超时',
  plan_timeout: '执行超时',
  tool_failed: '执行失败',
}

export const traceLabels = {
  database_query: '数据库查询', document_search: '材料问答（检索与生成）', formula_calculate: '公式计算',
  clarification: '澄清问题', database: '数据库工具', retrieval: '文档检索',
  schema_load: '读取数据库 Schema', sql_generate: '生成 SQL', sql_validate: 'SQL 安全校验',
  question_normalize: '问题标准化', elements_extract: '提取问题要素', semantic_validate: '语义校验',
  clarification_skipped: '无需澄清', schema_candidates_retrieved: '召回候选表和字段',
  schema_linking_completed: 'Schema Linking · 确定表和字段', join_path_planned: '规划真实外键路径',
  sql_repair_1: '首次有限修复', sql_repair_2: '最后一次修复', clarification_completed: '澄清完成',
  canonical_question_build: '生成标准问题', sql_execute: '执行只读查询', answer_generate: '生成回答',
  document_load: '读取文档', pdf_parse: '解析 PDF', chunk: '文本切片', embedding: '生成向量',
  vector_search: '检索与筛选资料', context_build: '构建资料上下文', llm_generate: '模型生成资料回答',
  multi_document_search: '联合检索材料', author_evidence: '提取作者依据',
  author_model_extract: '模型核对作者依据', original_excerpt: '定位原文节选',
  citation_validate: '校验资料引用', llm_recheck: '复核多材料回答',
  question_rewrite: '模型纠正问题',
}

export const latencyLabels = {
  routing_ms: '判断问题类型',
  planning_ms: '安排查询步骤',
  execution_ms: '查询数据与文档',
  fusion_ms: '核对多源依据',
  generation_ms: '组织回答',
  total_ms: '总耗时',
  llm_calls: '模型调用次数',
  prompt_tokens: '输入 Token',
  completion_tokens: '输出 Token',
  database_ms: '数据库工具',
  retrieval_ms: '文档检索工具',
  formula_ms: '公式工具',
  semantic_ms: '语义处理（含于数据库）',
  schema_linking_ms: 'Schema 定位（含于数据库）',
  sql_ms: 'SQL 生成与执行（含于数据库）',
}

export function stepLabel(stepId) {
  const number = Number(String(stepId || '').replace('step_', ''))
  return Number.isInteger(number) && number > 0 ? `第 ${number} 步` : stepId
}

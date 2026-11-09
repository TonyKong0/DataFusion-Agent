from app.core.errors import AppError


def validate_evidence(item: dict) -> dict:
    source = item.get('source_type')
    provenance = item.get('provenance') or {}
    if source == 'database' and (not provenance.get('sql') or not provenance.get('tables')):
        raise AppError('INVALID_EVIDENCE', '数据库证据缺少 SQL 或表名', 422)
    if source in ('document', 'formula', 'text') and (not isinstance(provenance.get('page'), int)
                                                    or not provenance.get('chunk_id') or not provenance.get('text')):
        raise AppError('INVALID_EVIDENCE', '文档证据缺少页码或原始片段', 422)
    if source in ('table', 'chart', 'image') and (not provenance.get('document_id')
              or not isinstance(provenance.get('page'), int) or not provenance.get('text')):
        raise AppError('INVALID_EVIDENCE', '多模态证据缺少文档、页码或原始内容', 422)
    if source == 'table' and (not isinstance(provenance.get('row_index'), int)
                              or not isinstance(provenance.get('column_index'), int)):
        raise AppError('INVALID_EVIDENCE', '表格证据缺少行列坐标', 422)
    if source == 'image' and not isinstance(provenance.get('image_index'), int):
        raise AppError('INVALID_EVIDENCE', '图片证据缺少图片序号', 422)
    if source == 'version_diff' and not (provenance.get('old_source') or provenance.get('new_source')):
        raise AppError('INVALID_EVIDENCE', '版本差异缺少原始文档来源', 422)
    if source not in ('database', 'document', 'text', 'formula', 'table', 'chart', 'image', 'version_diff'):
        raise AppError('INVALID_EVIDENCE', '未知证据来源', 422)
    return item

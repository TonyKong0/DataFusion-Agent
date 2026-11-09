import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.document_service import list_documents
from app.services.rag_service import query, UNKNOWN

if __name__ == '__main__':
    document_id = list_documents()[0]['document_id']
    result = query(document_id, '文本切片大小和重叠是多少？', 5)
    assert result['sources'] and any(source['page']==5 for source in result['sources'])
    assert '800' in result['answer'] and '120' in result['answer']
    unknown = query(document_id, '文档作者的电话号码是多少？', 5)
    assert unknown['answer']==UNKNOWN
    print('Phase 8 real RAG passed: page 5 citation and unknown-answer refusal')

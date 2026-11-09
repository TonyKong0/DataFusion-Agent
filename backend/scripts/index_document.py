import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.document_service import list_documents, load_document, document_path
from app.services.vector_store import build_index, search
import json

if __name__ == '__main__':
    document = load_document(list_documents()[0]['document_id'])
    build_index(document)
    document['status'] = 'indexed'
    document_path(document['document_id']).write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    hits = search(document, '文本切片大小和重叠是多少？', 5)
    assert any(hit['page']==5 for hit in hits)
    print('Phase 7 BGE + FAISS passed; retrieved page 5')

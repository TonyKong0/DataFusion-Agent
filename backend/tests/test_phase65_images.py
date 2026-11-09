from app.document.image import image_qa


def test_architecture_image_answer_keeps_image_location(monkeypatch):
    monkeypatch.setattr(image_qa, 'extract_images', lambda document_id: [
        {'document_id': document_id, 'filename': 'manual.pdf', 'page': 20, 'image_index': 2,
         'width': 500, 'height': 300, 'caption': '系统架构图', '_bytes': b'image'}])
    monkeypatch.setattr(image_qa, '_ocr_labels', lambda content: [
        {'text': 'Router', 'confidence': .9, 'bbox': []},
        {'text': 'Planner', 'confidence': .8, 'bbox': []}])
    result = image_qa.query_image('doc_x', '第20页第2张架构图包含哪些模块？')
    assert 'Router' in result['answer'] and 'Planner' in result['answer']
    assert result['image']['page'] == 20 and result['image']['image_index'] == 2
    assert '_bytes' not in result['image']

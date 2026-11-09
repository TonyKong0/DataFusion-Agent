from app.document.models import DocumentPage
from app.document.structure import llm_fallback


def test_llm_heading_fallback_rejects_hallucinated_title(monkeypatch):
    pages = [DocumentPage('d', 1, '研究目标\n本项目研究系统性能\n实施路线')]
    monkeypatch.setattr(llm_fallback, 'chat_json', lambda *_: {'headings': [
        {'title': '研究目标', 'page': 1, 'level': 1},
        {'title': '不存在的标题', 'page': 1, 'level': 2}]})
    headings = llm_fallback.fallback_headings(pages)
    assert [(h.title, h.level) for h in headings] == [('研究目标', 1)]

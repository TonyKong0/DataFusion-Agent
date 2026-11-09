from app.document.structure.heading_detector import detect_headings
from app.document.structure.hierarchy_builder import build_hierarchy


def reconstruct(document_id: str, pages: list) -> tuple[list[dict], dict]:
    headings = detect_headings(pages)
    tree = build_hierarchy(document_id, headings)
    return [item.to_dict() for item in headings], tree.to_dict()

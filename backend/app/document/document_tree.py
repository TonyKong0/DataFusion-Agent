from app.document.models import DocumentTree
from app.document.structure.heading_detector import detect_headings
from app.document.structure.hierarchy_builder import build_hierarchy
from app.document.structure.models import Heading


def build_tree(document_id: str, pages: list) -> DocumentTree:
    headings = ([Heading(**item) for page in pages for item in page.headings]
                if any(page.headings for page in pages) else detect_headings(pages))
    return build_hierarchy(document_id, headings) if headings else DocumentTree(document_id=document_id)

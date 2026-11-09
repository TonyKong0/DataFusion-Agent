from app.document.models import DocumentNode, DocumentTree


def build_hierarchy(document_id: str, headings: list) -> DocumentTree:
    root = DocumentTree(document_id)
    stack = []
    for heading in headings:
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        parent = stack[-1] if stack else None
        heading.parent = parent.title if parent else None
        node = DocumentNode(heading.title, heading.level, heading.page)
        (parent.children if parent else root.children).append(node)
        stack.append(node)
    return root

from app.document.inspector import inspect_pdf
from app.document.parser_router import parse
from app.document.document_tree import build_tree
from app.document.metadata import summarize_pages
from app.document.structure.heading_detector import detect_headings
from app.document.structure.llm_fallback import fallback_headings
from app.document.complexity.scorer import score_complexity
from app.document.formula.formula_detector import detect_formulas
from app.document.formula.parameter_linker import link_parameters
from app.document.formula.calculator import calculate_formula
from app.core.errors import AppError
from app.document.quality.assessor import assess_quality


def process_document(content: bytes, document_id: str) -> dict:
    inspection = inspect_pdf(content)
    precheck = score_complexity(inspection)
    pages = parse(content, document_id, inspection)
    enriched = [{**raw, 'text': page.text, 'text_blocks': len(page.blocks),
                 'was_scanned': bool(page.metadata.get('ocr_used'))}
                for raw, page in zip(inspection, pages)]
    complexity = score_complexity(enriched)
    if 'enable_ocr' in precheck['recommended_strategy'] and 'enable_ocr' not in complexity['recommended_strategy']:
        complexity['recommended_strategy'].append('enable_ocr')
    headings = detect_headings(pages)
    fallback_attempted = not headings and complexity['score'] >= 31
    if fallback_attempted:
        headings = fallback_headings(pages)
    for heading in headings:
        pages[heading.page - 1].headings.append(heading.to_dict())
    tree = build_tree(document_id, pages)
    quality = assess_quality(content, pages)
    heading_path = []
    path_by_page = {}
    for page in pages:
        for heading in page.headings:
            heading_path = heading_path[:heading['level'] - 1] + [heading['title']]
        path_by_page[page.page] = heading_path[:]
    formulas = []
    if 'enable_formula_parser' in complexity['recommended_strategy']:
        for formula in detect_formulas(pages):
            formula.heading_path = path_by_page.get(formula.page, [])
            binding = link_parameters(formula, pages)
            entry = {**formula.to_dict(), 'binding': binding}
            try:
                entry['calculation'] = calculate_formula(formula, binding)
            except AppError as error:
                entry['calculation_error'] = error.message
            formulas.append(entry)
            pages[formula.page - 1].formulas.append(entry)
    ocr_used = any(page.metadata.get('ocr_used') for page in pages)
    return {'pages': pages, 'tree': tree, 'metadata': summarize_pages(pages),
            'complexity': complexity, 'quality': quality, 'formulas': formulas,
            'trace': [{'step': 'document_inspected', 'status': 'success'},
                      {'step': 'scan_status_detected', 'status': 'success'},
                      {'step': 'complexity_scored', 'status': 'success'},
                      {'step': 'parser_selected', 'status': 'success'},
                      {'step': 'ocr_executed' if ocr_used else 'ocr_skipped', 'status': 'success'},
                      {'step': 'quality_assessed', 'status': 'success'},
                      {'step': 'heading_llm_fallback' if fallback_attempted else 'heading_rules_applied', 'status': 'success'},
                      {'step': 'heading_hierarchy_reconstructed', 'status': 'success'},
                      {'step': 'formula_detected', 'status': 'success'}]}

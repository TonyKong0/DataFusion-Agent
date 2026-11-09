from app.document.formula.parameter_extractor import extract_parameters


def link_parameters(formula, pages: list) -> dict:
    """Prefer the same page; retain ambiguity and do not search the whole document."""
    nearby = [page for page in pages if abs(page.page - formula.page) <= 1]
    binding = {}
    for variable in formula.variables:
        same_page = [page for page in nearby if page.page == formula.page]
        candidates = [candidate for page in same_page for candidate in
                      extract_parameters(page.text, variable, page.page, formula.raw_text, page.tables)]
        if not candidates:
            candidates = [candidate for page in nearby if page.page != formula.page for candidate in
                          extract_parameters(page.text, variable, page.page, formula.raw_text, page.tables)]
        if not candidates:
            binding[variable] = {'status': 'missing', 'candidates': []}
        elif len({(item.normalized_value, item.unit) for item in candidates}) > 1:
            binding[variable] = {'status': 'ambiguous', 'candidates': [item.to_dict() for item in candidates]}
        else:
            chosen = candidates[0]
            chosen.confidence = .96 if chosen.page == formula.page else .75
            chosen.candidates = [item.to_dict() for item in candidates[1:]]
            binding[variable] = {'status': 'bound', 'parameter': chosen.to_dict()}
    return binding

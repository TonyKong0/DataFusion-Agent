"""Run reproducible Phase 20 offline metrics from labelled JSON cases."""

import json
from pathlib import Path

from app.semantic.clarification_manager import create_clarification, resolve_clarification
from app.semantic.element_extractor import extract_rule_elements
from app.semantic.element_merger import merge_elements
from app.semantic.normalizer import normalize_question
from app.semantic.semantic_validator import validate_semantics


CASES = Path(__file__).parent / 'cases'


def load(name):
    return json.loads((CASES / name).read_text(encoding='utf-8'))


def extract(question):
    return merge_elements(extract_rule_elements(question))


def evaluate():
    normalization = load('normalization_cases.json')
    extraction = load('element_extraction_cases.json')
    clarification = load('clarification_cases.json')
    assert len(normalization) >= 30 and len(extraction) >= 30 and len(clarification) >= 30

    norm_errors = [case['question'] for case in normalization
                   if normalize_question(case['question'])['normalized_question'] != case['expected']]

    tp = fp = fn = 0
    extract_errors = []
    for case in extraction:
        predicted = {(item.type, item.name, json.dumps(item.canonical_value, ensure_ascii=False))
                     for item in extract(case['question'])['elements']}
        expected = {(kind, name, json.dumps(value, ensure_ascii=False))
                    for kind, name, value in case['expected']}
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        if predicted != expected:
            extract_errors.append(case['question'])

    positive = negative = found = false_positive = resume_success = answerable = 0
    clarification_errors = []
    for case in clarification:
        question = case['question']
        validation = validate_semantics(question, extract(question))
        predicted = validation['need_clarification']
        if case['clarify']:
            positive += 1
            found += predicted
        else:
            negative += 1
            false_positive += predicted
        if predicted != case['clarify']:
            clarification_errors.append(question)
        if predicted and case.get('answer'):
            answerable += 1
            card = create_clarification(question, validation)
            try:
                resolved = resolve_clarification(card['session_id'], case['answer'])
                resumed = validate_semantics(resolved['question'], extract(resolved['question']),
                                             confirmed=resolved['confirmed'])
                resume_success += resumed['valid']
            except Exception:
                pass

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        'normalization': {'cases': len(normalization), 'correct': len(normalization) - len(norm_errors),
                          'accuracy': (len(normalization) - len(norm_errors)) / len(normalization),
                          'errors': norm_errors},
        'element_extraction': {'cases': len(extraction), 'tp': tp, 'fp': fp, 'fn': fn,
                               'precision': precision, 'recall': recall,
                               'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0,
                               'errors': extract_errors},
        'clarification': {'cases': len(clarification), 'positives': positive, 'negatives': negative,
                          'recall': found / positive, 'false_clarification_rate': false_positive / negative,
                          'success_rate': resume_success / answerable if answerable else 0,
                          'answerable': answerable, 'errors': clarification_errors},
    }


if __name__ == '__main__':
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))

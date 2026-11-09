"""Reproducible, controlled V4 document benchmark; no production data is modified."""
import json
import time
import argparse
from pathlib import Path
import pymupdf
from app.document.models import DocumentPage
from app.document.formula.formula_detector import detect_formulas
from app.document.formula.parameter_linker import link_parameters
from app.document.formula.calculator import calculate_formula
from app.document.native_pdf_parser import parse_native
from app.document.structure.heading_detector import detect_headings
from app.document.structure.hierarchy_builder import build_hierarchy
from app.document.structure.chunking import split_hierarchical
from app.document.complexity.scorer import score_complexity
from app.document.quality.text_quality import detect_text_issues
from app.document.quality.assessor import assess_quality
from app.services.text_splitter import split_pages

ROOT = Path(__file__).resolve().parents[2]


def formula_benchmark():
    results = []
    for group in range(4):
        for index in range(5):
            current = 120 + index * 20
            previous = 100 + index * 10
            if group == 0:
                raw, expected, unit = '增长率=(本期值-上期值)/上期值×100%', (current-previous)/previous*100, '%'
            elif group == 1:
                raw, expected, unit = '差额=本期值-上期值', (current-previous)*10000, ''
            elif group == 2:
                raw, expected, unit = '总额=本期值+上期值', (current+previous)*10000, ''
            else:
                raw, expected, unit = '倍数=本期值/上期值', current/previous, ''
            page = DocumentPage('test', index+1,
                f'{raw}\n本期值为{current}万元\n上期值为{previous}万元')
            candidates = detect_formulas([page])
            predicted = set(candidates[0].variables) if candidates else set()
            binding = link_parameters(candidates[0], [page]) if candidates else {}
            result = calculate_formula(candidates[0], binding) if candidates else None
            gold = {'本期值', '上期值'}
            results.append({'case': f'{group+1}-{index+1}', 'formula': raw,
                'parameter_tp': len(predicted & gold), 'parameter_fp': len(predicted-gold),
                'parameter_fn': len(gold-predicted),
                'binding_correct': all(binding.get(name, {}).get('status') == 'bound' and
                    binding[name]['parameter']['normalized_value'] == value and
                    binding[name]['parameter']['page'] == index+1
                    for name, value in [('本期值', current), ('上期值', previous)]),
                'parse_correct': bool(result and result['unit'] == unit),
                'calculation_correct': bool(result and abs(result['result']-expected) < 1e-6)})
    tp = sum(r['parameter_tp'] for r in results)
    fp = sum(r['parameter_fp'] for r in results)
    fn = sum(r['parameter_fn'] for r in results)
    precision = tp / (tp+fp) if tp+fp else 0
    recall = tp / (tp+fn) if tp+fn else 0
    return {'cases': results, 'metrics': {'count': len(results), 'parameter_precision': precision,
        'parameter_recall': recall, 'parameter_f1': 2*precision*recall/(precision+recall) if precision+recall else 0,
        'binding_accuracy': sum(r['binding_correct'] for r in results)/len(results),
        'formula_parse_accuracy': sum(r['parse_correct'] for r in results)/len(results),
        'calculation_accuracy': sum(r['calculation_correct'] for r in results)/len(results)}}


def _make_heading_pdf(index: int) -> bytes:
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        major_pairs = [
            ('1. Overview', '2. Results'), ('1) Overview', '2) Results'),
            ('Chapter 1 Overview', 'Chapter 2 Results'), ('Part I Overview', 'Part II Results'),
            ('SECTION 1 Overview', 'SECTION 2 Results'), ('I. Overview', 'II. Results'),
            ('A. Overview', 'B. Results'), ('1 - Overview', '2 - Results'),
            ('1 Overview', '2 Results'), ('1. Introduction', '2. Analysis')]
        major1, major2 = major_pairs[index]
        lines = [major1, '1.1 Scope', '1.1.1 Goal', major2, '2.1 Findings']
        for j, line in enumerate(lines):
            page.insert_text((72, 90 + j * (60 if index % 3 else 75)), line,
                             fontsize=16 if j in (0, 3) and index % 2 else 12)
        return pdf.tobytes()


def heading_benchmark():
    results = []
    gold_levels = [1, 2, 3, 1, 2]
    for index in range(10):
        pages = parse_native(_make_heading_pdf(index), f'heading_{index}')
        headings = detect_headings(pages)
        tree = build_hierarchy(f'heading_{index}', headings)
        levels = [h.level for h in headings]
        hierarchy_ok = (levels == gold_levels and len(tree.children) == 2 and
                        len(tree.children[0].children[0].children) == 1)
        results.append({'document': index+1, 'format': f'numbered-layout-{index+1}',
                        'detected': levels, 'heading_tp': min(len(levels), 5) if levels == gold_levels else 0,
                        'heading_fp': max(len(levels)-5, 0), 'heading_fn': 0 if levels == gold_levels else 5,
                        'hierarchy_correct': hierarchy_ok})
    tp = sum(r['heading_tp'] for r in results)
    fp = sum(r['heading_fp'] for r in results)
    fn = sum(r['heading_fn'] for r in results)
    return {'cases': results, 'metrics': {'documents': 10, 'heading_precision': tp/(tp+fp),
        'heading_recall': tp/(tp+fn), 'hierarchy_accuracy': sum(r['hierarchy_correct'] for r in results)/10}}


def complexity_benchmark():
    results = []
    for index in range(20):
        group, variant = divmod(index, 5)
        gold_level = ['Low', 'Medium', 'High', 'Very High'][group]
        pages = [1 + variant, 1 + variant, 5 + variant, 50 + variant][group]
        rich_text = '第一章 简介\n1.1 方法\n1.1.1 结果\n' + ('增长率=(本期值-上期值)/上期值×100%\n' * 8)
        inspections = [{'page': page+1,
            'text': rich_text if group >= 2 and page == 0 else '普通正文',
            'text_blocks': (10 if page % 2 else 0) if group == 3 else 3,
            'image_count': 4 if group == 2 else 1 if group in (1, 3) else 0,
            'image_ratio': .9 if group else 0,
            'was_scanned': group > 0} for page in range(pages)]
        scored = score_complexity(inspections)
        selected = scored['recommended_strategy']
        correct = (('enable_ocr' in selected) == (group > 0) and
                   ('enable_formula_parser' in selected) == (group >= 2) and
                   ('hierarchical_chunking' in selected) == (group > 0))
        results.append({'document': index+1, 'score': scored['score'], 'level': scored['level'],
                        'gold_level': gold_level, 'strategy': selected, 'strategy_correct': correct})
    stable = all(score_complexity([{'page': 1, 'text': '普通正文', 'text_blocks': 3,
        'image_count': 0, 'image_ratio': 0}])['score'] == 0 for _ in range(5))
    return {'cases': results, 'metrics': {'documents': 20,
        'strategy_accuracy': sum(r['strategy_correct'] for r in results)/20,
        'score_repeat_stable': stable,
        'level_agreement': sum(r['level'] == r['gold_level'] for r in results)/20,
        'level_agreement_note': '与预先设定的四档合成场景标签比较，不是独立真实文档人工评分'}}


def quality_benchmark():
    cases = [
        (DocumentPage('d', 1, '普通正文足够长，且没有异常字符。这是一段正常的页面内容。'), set()),
        (DocumentPage('d', 2, ''), {'blank_page'}),
        (DocumentPage('d', 3, '文字\ufffd\ufffd\ufffd'), {'anomalous_characters', 'suspected_typo', 'low_text'}),
        (DocumentPage('d', 4, 'High contrast scanned page text', metadata={'ocr_used': True, 'ocr_confidence': .42}), {'scanned_page', 'low_ocr_confidence'}),
        (DocumentPage('d', 5, '简短'), {'low_text'}),
        (DocumentPage('d', 6, 'A rotated page with sufficient text.', metadata={'rotation': 90}), {'rotation'}),
        (DocumentPage('d', 7, 'High contrast scanned page text', metadata={'ocr_used': True, 'ocr_confidence': .9}), {'scanned_page'}),
        (DocumentPage('d', 8, '', metadata={'ocr_used': True, 'ocr_confidence': .9}), {'scanned_page', 'blank_page', 'blur'}),
    ]
    with pymupdf.open() as pdf:
        for index in range(8):
            page = pdf.new_page()
            if index in (3, 6):
                page.insert_text((50, 170), 'HIGH CONTRAST SCANNED PAGE TEXT', fontsize=34)
                page.insert_text((50, 250), 'MORE PRINTED WORDS 12345', fontsize=30)
        content = pdf.tobytes()
    assessed = assess_quality(content, [page for page, _ in cases])
    tp = fp = fn = 0
    results = []
    for page, gold in cases:
        predicted = {issue['type'] for issue in assessed['issues'] if issue['page'] == page.page}
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
        results.append({'page': page.page, 'expected': sorted(gold), 'predicted': sorted(predicted)})
    return {'cases': results, 'metrics': {'issue_precision': tp/(tp+fp) if tp+fp else 0,
        'issue_recall': tp/(tp+fn) if tp+fn else 0,
        'pages': 8, 'coverage': 'normal, rotation, blur, scanned, anomalous, blank and low OCR confidence; controlled pages'}}


def rag_comparison():
    """Controlled lexical retrieval proxy, not a claim about LLM answer quality."""
    results = []
    for index in range(10):
        fact = f'PROJECT{index}BUDGET{100+index}'
        pages = [DocumentPage('d', 1, '1. Overview\n' + 'background ' * 70 +
            '\n1.1 Budget\n' + fact + '\n' + 'details ' * 40)]
        fixed = split_pages([{'page': 1, 'text': pages[0].text}], 'd', 'test.pdf')
        hierarchical = split_hierarchical(pages, 'd', 'test.pdf')
        def rank(chunks):
            return sorted(chunks, key=lambda c: (fact in c['text'], 'Budget' in c['text']), reverse=True)[0]
        start = time.perf_counter(); old_hit = rank(fixed); old_ms = (time.perf_counter()-start)*1000
        start = time.perf_counter(); new_hit = rank(hierarchical); new_ms = (time.perf_counter()-start)*1000
        results.append({'case': index+1, 'fixed_hit': fact in old_hit['text'],
                        'v4_hit': fact in new_hit['text'], 'v4_heading_correct': new_hit.get('heading_path', [])[-1:] == ['1.1 Budget'],
                        'fixed_latency_ms': old_ms, 'v4_latency_ms': new_ms})
    return {'cases': results, 'metrics': {'fixed_hit_rate': sum(r['fixed_hit'] for r in results)/10,
        'v4_hit_rate': sum(r['v4_hit'] for r in results)/10,
        'v4_heading_source_accuracy': sum(r['v4_heading_correct'] for r in results)/10,
        'fixed_avg_rank_ms': sum(r['fixed_latency_ms'] for r in results)/10,
        'v4_avg_rank_ms': sum(r['v4_latency_ms'] for r in results)/10,
        'answer_accuracy': None, 'note': '词面检索代理测试；未调用 BGE-M3 或 DeepSeek，不能代表真实 RAG 准确率'}}


def evaluate():
    return {'formula': formula_benchmark(), 'headings': heading_benchmark(),
            'complexity': complexity_benchmark(), 'quality': quality_benchmark(),
            'rag_proxy': rag_comparison()}


def rag_live_comparison():
    """BGE-M3 + DeepSeek on controlled facts; real calls, synthetic documents."""
    import numpy as np
    from app.services.embedding_service import embed
    from app.llm.deepseek_client import chat_json
    from app.llm.prompts import RAG_SYSTEM
    cases = []
    for index in range(10):
        name = f'Project{index}'
        amount = 100 + index * 7
        page = DocumentPage('d', 1, '1. Overview\n' + ('General background. ' * 35) +
            f'\n1.1 Budget\nThe budget of {name} is {amount} USD.\n' + ('Additional notes. ' * 25))
        fixed = split_pages([{'page': 1, 'text': page.text}], 'd', 'test.pdf')
        hierarchy = split_hierarchical([page], 'd', 'test.pdf')
        cases.append({'question': f'What is the budget of {name}?', 'amount': amount,
                      'fixed': fixed, 'v4': hierarchy})
    all_texts = [chunk['text'] for case in cases for mode in ('fixed', 'v4') for chunk in case[mode]]
    questions = [case['question'] for case in cases]
    vectors = embed(all_texts + questions)
    offset = 0
    records = []
    for index, case in enumerate(cases):
        record = {'case': index+1, 'question': case['question'], 'gold': case['amount']}
        for mode in ('fixed', 'v4'):
            chunks = case[mode]
            start = time.perf_counter()
            scores = np.matmul(vectors[offset:offset+len(chunks)], vectors[len(all_texts)+index])
            hit = chunks[int(np.argmax(scores))]
            context = [{'chunk_id': hit['chunk_id'], 'page': hit['page'],
                        'heading_path': hit.get('heading_path', []), 'text': hit['text']}]
            response = chat_json(RAG_SYSTEM, json.dumps({'question': case['question'], 'context': context}, ensure_ascii=False))
            record[mode] = {'hit': f"{case['amount']} USD" in hit['text'],
                'answer_correct': str(case['amount']) in response.get('answer', ''),
                'source_correct': hit['chunk_id'] in response.get('used_chunk_ids', []) and hit['page'] == 1,
                'latency_ms': round((time.perf_counter()-start)*1000),
                'heading_path': hit.get('heading_path', []), 'answer': response.get('answer', '')}
            offset += len(chunks)
        records.append(record)
    metrics = {}
    for mode in ('fixed', 'v4'):
        metrics[mode] = {'retrieval_hit_rate': sum(r[mode]['hit'] for r in records)/10,
            'answer_accuracy': sum(r[mode]['answer_correct'] for r in records)/10,
            'source_accuracy': sum(r[mode]['source_correct'] for r in records)/10,
            'avg_retrieval_answer_latency_ms': round(sum(r[mode]['latency_ms'] for r in records)/10)}
    return {'cases': records, 'metrics': metrics,
            'note': 'Controlled synthetic English PDF text; does not measure scanned Chinese PDF generalization.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='also call local BGE-M3 and DeepSeek')
    args = parser.parse_args()
    output = evaluate()
    if args.live:
        output['rag_live'] = rag_live_comparison()
    path = ROOT / ('docs/evaluation_document_v4_live.json' if args.live
                   else 'docs/evaluation_document_v4_results.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: section['metrics'] for key, section in output.items()}, ensure_ascii=False, indent=2))

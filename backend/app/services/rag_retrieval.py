"""Bounded dense/lexical candidate retrieval from the selected document only."""
import math
import re
from collections import Counter

from app.services.vector_store import search

_REQUEST_WORDS = re.compile(
    r'所选|选中|当前|文档|材料|文章|资料|这几篇|这篇|这些|请问|请|帮我|'
    r'如何|怎么|介绍|概括|总结|主要内容|讲的是什么|是什么|有哪些|有哪|'
    r'为什么|在哪里|哪里人|哪里|什么时候|是谁|干嘛|什么|分别|比较|对比|不同|区别')
_NOISE = re.compile(r'PPT模板|模板网|WWW\.|www\.', re.I)
_EXERCISE_REQUEST = re.compile(r'练习|习题|思考题|课后题|题目|提出.{0,4}问题')


def query_terms(question: str) -> list[str]:
    """Character n-grams support unseen Chinese names without an alias dictionary."""
    text = _REQUEST_WORDS.sub(' ', question.casefold())
    terms = set(re.findall(r'[a-z0-9][a-z0-9_.-]*', text))
    for phrase in re.findall(r'[\u4e00-\u9fff]+', text):
        for size in (2, 3, 4):
            terms.update(phrase[start:start + size] for start in range(len(phrase)-size+1))
    return sorted(terms, key=lambda term: (-len(term), term))[:64]


def lexical_scores(chunks: list[dict], question: str) -> dict[str, float]:
    terms = query_terms(question)
    if not chunks or not terms:
        return {}
    texts = [str(chunk.get('text') or '').casefold() for chunk in chunks]
    average_length = max(1, sum(map(len, texts))/len(texts))
    counts = [{term: text.count(term) for term in terms if term in text} for text in texts]
    frequencies = Counter(term for row in counts for term in row)
    scores = {}
    for chunk, text, row in zip(chunks, texts, counts):
        score = 0.0
        for term, count in row.items():
            idf = math.log(1+(len(chunks)-frequencies[term]+.5)/(frequencies[term]+.5))
            score += idf * count * 2.2 / (count+1.2*(.25+.75*len(text)/average_length))
        if score:
            scores[chunk['chunk_id']] = score
    return scores


def evidence_penalty(text: str, question: str) -> float:
    body = text.strip()
    penalty = .25 if _NOISE.search(body) else 0.0
    # Do not discard short complete facts such as a signature or a numeric value.
    if (len(body) < 35 and not re.search(r'[。！？!?：:；;]', body)
            and not re.search(r'\d+(?:\.\d+)?\s*(?:元|人|个|条|年|月|日|%|％)', body)):
        penalty += .24
    last_question = max(body.rfind('？'), body.rfind('?'))
    if (('？' in body or '?' in body) and not _EXERCISE_REQUEST.search(question)
            and len(body[last_question+1:].strip()) < 15
            and not re.search(r'[。；]|答[:：]|因为|因此|表明|体现', body)):
        penalty += .18
    return penalty


def retrieve_candidates(document: dict, question: str, limit: int, *, search_fn=search) -> list[dict]:
    chunks = document.get('content') or []
    sparse = lexical_scores(chunks, question)
    pool_size = max(20, min(60, limit*4))
    lexical_ids = set(sorted(sparse, key=sparse.get, reverse=True)[:pool_size])
    try:
        hits = search_fn(document, question, pool_size, extra_chunk_ids=lexical_ids)
    except TypeError as error:
        if 'extra_chunk_ids' not in str(error):
            raise
        hits = search_fn(document, question, pool_size)
    maximum = max(sparse.values(), default=1.0)
    for hit in hits:
        dense = float(hit.get('score') or 0)
        lexical = sparse.get(hit['chunk_id'], 0)/maximum
        hit['retrieval_score'] = round(dense+.12*lexical-evidence_penalty(hit['text'], question), 4)
        hit['retrieval_method'] = 'dense_lexical'
    hits.sort(key=lambda hit: (-hit['retrieval_score'], -len(hit['text']), hit['chunk_id']))
    return hits[:limit]

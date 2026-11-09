"""Session-local episodic retrieval and deterministic context packing."""
from copy import deepcopy
import json

import faiss
import numpy as np

from app.agent.budget import estimate_tokens
from app.services.embedding_service import embed


EPISODIC_MIN_SCORE = 0.30
EPISODIC_MAX_TURNS = 3
MEMORY_CANDIDATE_LIMIT = 200


def scope_key(mode: str, document_ids: list[str] | None) -> str:
    return mode + ':' + json.dumps(sorted(set(document_ids or [])), ensure_ascii=False)


def _document_ids(turn: dict) -> list[str]:
    result = turn.get('result') or {}
    ids = result.get('document_ids')
    if not isinstance(ids, list):
        ids = [result['document_id']] if result.get('document_id') else []
    return sorted({item for item in ids if isinstance(item, str)})


def scope_matches(turn: dict, mode: str, document_ids: list[str] | None) -> bool:
    if (turn.get('result') or {}).get('conversation_history'):
        return False
    stored = _document_ids(turn)
    if mode == 'rag':
        return stored == sorted(set(document_ids or []))
    if mode == 'agent':
        # Keep database-only memories for cross-source follow-ups, but never
        # import facts from a different material selection.
        if not stored:
            return True
        return stored == sorted(set(document_ids or []))
    return True


def _memory_text(turn: dict) -> str:
    result = turn.get('result') or {}
    route = (result.get('route') or {}).get('route')
    parts = [turn.get('question') or '', turn.get('resolved_question') or '',
             str(turn.get('answer') or '')[:500]]
    if route:
        parts.append(f'来源路径：{route}')
    names = result.get('document_names') or []
    if names:
        parts.append('材料：' + '、'.join(
            item.get('filename', '') for item in names if isinstance(item, dict)))
    return '\n'.join(part for part in parts if part)


def retrieve_episodic(turns: list[dict], question: str, *, mode: str,
                      document_ids: list[str] | None, recent_turn_ids: set,
                      limit: int = EPISODIC_MAX_TURNS) -> list[dict]:
    """Retrieve semantically related older turns from this conversation only."""
    candidates = [turn for turn in turns
                  if turn.get('id') not in recent_turn_ids
                  and scope_matches(turn, mode, document_ids)]
    candidates = candidates[-MEMORY_CANDIDATE_LIMIT:]
    if not candidates or limit <= 0:
        return []
    texts = [_memory_text(turn) for turn in candidates]
    try:
        vectors = np.asarray(embed([question, *texts]), dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts) + 1 or not vectors.shape[1]:
            return []
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors[1:])
        scores, positions = index.search(vectors[:1], min(limit, len(candidates)))
    except Exception:
        # Conversation memory is an enhancement; missing local embeddings must
        # not prevent the normal recent-history path from answering.
        return []

    selected = []
    for score, position in zip(scores[0], positions[0]):
        if position < 0 or float(score) < EPISODIC_MIN_SCORE:
            continue
        turn = candidates[int(position)]
        result = turn.get('result') or {}
        route = (result.get('route') or {}).get('route')
        selected.append({
            'turn_id': turn.get('id'),
            'question': str(turn.get('question') or '')[:300],
            'resolved_question': str(turn.get('resolved_question') or '')[:400],
            'answer': str(turn.get('answer') or '')[:500],
            'source_route': route,
            'document_ids': _document_ids(turn),
        })
    return selected


def estimate_context(system: str, payload: dict) -> int:
    # Match the exact JSON encoding sent by conversation.service._rewrite so
    # compaction cannot underestimate the prompt at a configured budget edge.
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    return estimate_tokens(system + serialized)


def fit_rewrite_context(payload: dict, system: str, max_tokens: int) -> dict:
    """Trim low-priority stored memory while preserving the live question."""
    fitted = deepcopy(payload)
    episodes = fitted.get('episodic_memory')
    while estimate_context(system, fitted) > max_tokens and isinstance(episodes, list) and episodes:
        episodes.pop()  # retrieval is sorted by relevance, least relevant is last

    recent = fitted.get('recent')
    while (estimate_context(system, fitted) > max_tokens
           and isinstance(recent, list) and len(recent) > 1):
        recent.pop(0)

    summary = fitted.get('summary')
    while estimate_context(system, fitted) > max_tokens and isinstance(summary, str) and summary:
        summary = summary[max(1, len(summary) // 3):]
        fitted['summary'] = summary

    recent = fitted.get('recent')
    while estimate_context(system, fitted) > max_tokens and isinstance(recent, list) and recent:
        if len(recent) > 1:
            recent.pop(0)
            continue
        changed = False
        for key in ('answer', 'resolved_question', 'question'):
            value = recent[0].get(key)
            if isinstance(value, str) and value:
                recent[0][key] = value[:max(0, len(value) // 2)]
                changed = True
                break
        if not changed:
            recent.pop()
    return fitted

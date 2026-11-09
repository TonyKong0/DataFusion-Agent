"""Short-lived, process-local clarification sessions."""

import threading
import time
from uuid import uuid4

from app.core.errors import AppError
from app.semantic.config_loader import load_config


_SESSIONS: dict[str, dict] = {}
_LOCK = threading.Lock()


def create_clarification(question: str, validation: dict, original_question: str | None = None) -> dict:
    rules = load_config('clarification_rules.yaml')['rules']
    if 'entity' in validation['missing'] or 'entity' in validation['ambiguities']:
        kind, prompt, options = 'single_choice', rules['entity_prompt'], rules['entity_choices']
    elif 'time_range' in validation['missing']:
        kind, prompt, options = 'free_text', rules['time_prompt'], []
    elif validation['low_confidence'] and not (validation['unsupported'] or validation['conflicts'] or validation['error']):
        kind, prompt, options = 'confirm', rules['confirm_prompt'], ['确认', '取消']
    else:
        kind, prompt, options = 'free_text', rules['free_text_prompt'], []
    session_id = uuid4().hex
    now = time.monotonic()
    with _LOCK:
        for key, saved in list(_SESSIONS.items()):
            if saved['expires_at'] <= now:
                del _SESSIONS[key]
        if len(_SESSIONS) >= rules['max_sessions']:
            oldest = min(_SESSIONS, key=lambda key: _SESSIONS[key]['expires_at'])
            del _SESSIONS[oldest]
        _SESSIONS[session_id] = {'question': question, 'original_question': original_question or question,
                                 'kind': kind, 'options': options,
                                 'replace_question': bool((validation['unsupported'] or validation['conflicts'] or validation['error'])
                                                          and 'time_range' not in validation['missing']),
                                 'ambiguous_entity': 'entity' in validation['ambiguities'],
                                 'expires_at': now + rules['ttl_seconds']}
    return {'session_id': session_id, 'kind': kind, 'question': prompt, 'options': options}


def resolve_clarification(session_id: str, answer: str) -> dict:
    answer = answer.strip()
    with _LOCK:
        saved = _SESSIONS.get(session_id)
        if not saved or saved['expires_at'] <= time.monotonic():
            _SESSIONS.pop(session_id, None)
            raise AppError('CLARIFICATION_EXPIRED', '澄清会话已过期，请重新提问', 404)
        if saved['kind'] in {'single_choice', 'confirm'} and answer not in saved['options']:
            raise AppError('INVALID_CLARIFICATION', '请选择提供的选项', 422)
        if not answer:
            raise AppError('INVALID_CLARIFICATION', '请填写补充内容', 422)
        del _SESSIONS[session_id]
    if saved['kind'] == 'confirm':
        return {'question': saved['question'], 'original_question': saved['original_question'],
                'confirmed': answer == '确认', 'cancelled': answer == '取消'}
    if saved['replace_question'] and saved['kind'] == 'free_text':
        return {'question': answer, 'original_question': saved['original_question'],
                'confirmed': False, 'cancelled': False}
    if saved['ambiguous_entity'] and saved['kind'] == 'single_choice':
        question = saved['question']
        for option in saved['options']:
            if option != answer:
                question = question.replace(option, '')
        question = question.strip(' 和或、，, ')
        return {'question': question, 'original_question': saved['original_question'],
                'confirmed': False, 'cancelled': False}
    return {'question': f"{saved['question']} {answer}",
            'original_question': saved['original_question'], 'confirmed': False, 'cancelled': False}

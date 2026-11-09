import json
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4
from app.core.errors import AppError


_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
_MEMORY_KEYS = {'summary', 'recent', 'history', 'episodic_memory', 'working_memory', 'memory',
                'previous_summary', 'turns', 'pending_question'}
_QUESTION_KEYS = {'question', 'current_question', 'standalone_question', 'original_question'}
_EVIDENCE_KEYS = {'context', 'schema', 'sources', 'evidence', 'documents', 'rows', 'results'}


def estimate_tokens(text: str) -> int:
    """Conservatively estimate prompt tokens without a provider-specific tokenizer."""
    value = str(text or '')
    if not value:
        return 0
    cjk = len(_CJK.findall(value))
    return math.ceil(cjk * 1.2 + (len(value) - cjk) / 3)


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def _prompt_breakdown(system: str, user: str) -> tuple[int, dict[str, int]]:
    total = estimate_tokens(system + user)
    breakdown = {'system_prompt': estimate_tokens(system), 'conversation_memory': 0,
                 'current_question': 0, 'source_evidence': 0, 'other_payload': 0}
    try:
        payload = json.loads(user)
    except (json.JSONDecodeError, TypeError):
        breakdown['current_question'] = estimate_tokens(user)
    else:
        if isinstance(payload, dict):
            for key, value in payload.items():
                category = ('conversation_memory' if key in _MEMORY_KEYS else
                            'current_question' if key in _QUESTION_KEYS else
                            'source_evidence' if key in _EVIDENCE_KEYS else 'other_payload')
                breakdown[category] += estimate_tokens(_json_text(value))
        else:
            breakdown['other_payload'] = estimate_tokens(_json_text(payload))
    accounted = sum(breakdown.values())
    breakdown['other_payload'] += max(0, total - accounted)
    return total, breakdown


@dataclass
class LLMBudget:
    maximum: int
    timeout: int
    context_tokens: int
    max_total_tokens: int | None = None
    used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    _reserved_tokens: int = 0
    reported_requests: int = 0
    estimated_peak_tokens: int = 0
    actual_peak_tokens: int = 0
    peak_breakdown: dict = field(default_factory=dict)
    _last_breakdown: dict = field(default_factory=dict)
    _calls: list[dict] = field(default_factory=list)
    _scoped_limits: list[tuple[str, int, int]] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)

    def consume(self, user: str, *, system: str = '', max_completion_tokens: int = 0):
        estimate, breakdown = _prompt_breakdown(system, user)
        if estimate > self.context_tokens:
            raise AppError('CONTEXT_BUDGET_EXCEEDED', '输入上下文超过当前请求预算', 422)
        if max_completion_tokens < 0:
            raise ValueError('max_completion_tokens cannot be negative')
        with self.lock:
            if (self.used >= self.maximum
                    or any(self.used - start >= maximum
                           for _, start, maximum in self._scoped_limits)):
                raise AppError('LLM_BUDGET_EXCEEDED', '当前请求的大模型调用预算已用完', 429)
            reservation = (estimate + max_completion_tokens
                           if self.max_total_tokens is not None else 0)
            if (self.max_total_tokens is not None
                    and self.prompt_tokens + self.completion_tokens
                    + self._reserved_tokens + reservation > self.max_total_tokens):
                raise AppError('LLM_TOKEN_BUDGET_EXCEEDED', '本次评测的 Token 总预算已用完', 429)
            self.used += 1
            self._reserved_tokens += reservation
            self._last_breakdown = breakdown
            self._calls.append({'estimated_tokens': estimate, 'actual_tokens': None,
                                'completion_tokens': None, 'reserved_tokens': reservation,
                                'breakdown': dict(breakdown)})
            if estimate > self.estimated_peak_tokens:
                self.estimated_peak_tokens = estimate
                self.peak_breakdown = dict(breakdown)

    def push_call_limit(self, maximum: int) -> str:
        scope_id = uuid4().hex
        with self.lock:
            self._scoped_limits.append((scope_id, self.used, maximum))
        return scope_id

    def pop_call_limit(self, scope_id: str) -> None:
        with self.lock:
            self._scoped_limits = [scope for scope in self._scoped_limits if scope[0] != scope_id]

    def record_usage(self, prompt_tokens: int, completion_tokens: int):
        with self.lock:
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.reported_requests += 1
            if self._calls:
                call = self._calls[-1]
                self._reserved_tokens -= call['reserved_tokens']
                call['reserved_tokens'] = 0
                call['actual_tokens'] = prompt_tokens
                call['completion_tokens'] = completion_tokens
            if prompt_tokens > self.actual_peak_tokens:
                self.actual_peak_tokens = prompt_tokens
                self.peak_breakdown = dict(self._last_breakdown)

    def token_budget_usage(self) -> dict:
        with self.lock:
            provider_tokens = self.prompt_tokens + self.completion_tokens
            budgeted_tokens = provider_tokens + self._reserved_tokens
            return {
                'maximum_tokens': self.max_total_tokens,
                'provider_reported_tokens': provider_tokens,
                'reserved_tokens_without_usage': self._reserved_tokens,
                'budgeted_tokens': budgeted_tokens,
                'remaining_tokens': (max(0, self.max_total_tokens - budgeted_tokens)
                                     if self.max_total_tokens is not None else None),
                'exceeded': (self.max_total_tokens is not None
                             and budgeted_tokens > self.max_total_tokens),
            }

    def context_usage(self, start_attempt: int = 0) -> dict:
        with self.lock:
            calls = self._calls[max(0, start_attempt):]
            reported = [call for call in calls if call['actual_tokens'] is not None]
            has_complete_usage = bool(calls) and len(reported) == len(calls)
            measurement = 'provider' if has_complete_usage else 'estimate'
            estimated_peak = max((call['estimated_tokens'] for call in calls), default=0)
            actual_peak = max((call['actual_tokens'] for call in reported), default=0)
            used = actual_peak if has_complete_usage else estimated_peak
            peak_call = (max(calls, key=lambda call: call['actual_tokens'] or 0)
                         if has_complete_usage else
                         max(calls, key=lambda call: call['estimated_tokens']) if calls else None)
            return {
                'budget_tokens': self.context_tokens,
                'used_tokens': used,
                'remaining_tokens': max(0, self.context_tokens - used),
                'measurement': measurement,
                'estimated_peak_tokens': estimated_peak,
                'actual_peak_tokens': actual_peak if reported else None,
                'total_prompt_tokens': sum(call['actual_tokens'] for call in reported) if reported else None,
                'total_completion_tokens': sum(call['completion_tokens'] for call in reported) if reported else None,
                'api_requests': len(calls),
                'reported_requests': len(reported),
                'status': 'ready' if calls else 'no_model_call',
                'breakdown': dict(peak_call['breakdown']) if peak_call else {},
            }


_current: ContextVar[LLMBudget | None] = ContextVar('agent_llm_budget', default=None)


def current_budget():
    return _current.get()


@contextmanager
def request_budget(maximum: int, timeout: int, context_tokens: int,
                   max_total_tokens: int | None = None):
    existing = current_budget()
    if existing is not None:
        scope_id = existing.push_call_limit(maximum)
        try:
            yield existing
        finally:
            existing.pop_call_limit(scope_id)
        return
    budget = LLMBudget(maximum, timeout, context_tokens, max_total_tokens)
    token = _current.set(budget)
    try:
        yield budget
    finally:
        _current.reset(token)

"""Request-scoped, credential-free accounting for provider usage metadata."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class LLMUsage:
    api_requests: int = 0
    reported_requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        return {'api_requests': self.api_requests,
                'reported_requests': self.reported_requests,
                'prompt_tokens': self.prompt_tokens,
                'completion_tokens': self.completion_tokens,
                'total_tokens': self.total_tokens}


_current: ContextVar[LLMUsage | None] = ContextVar('llm_usage', default=None)


def current_usage() -> LLMUsage | None:
    return _current.get()


@contextmanager
def collect_usage():
    existing = current_usage()
    if existing is not None:
        yield existing
        return
    usage = LLMUsage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)

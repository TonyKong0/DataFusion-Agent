"""Semantic processing layer for V2 structured questions.

Phase 11 only establishes the boundary; V1 request flows do not use it yet.
"""

from app.semantic.models import SemanticRequest

__all__ = ['SemanticRequest']

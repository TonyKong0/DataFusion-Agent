"""Conversation API layered over the existing query routes."""
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.conversation import store, service, cancellation
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.document_service import load_document

router = APIRouter(prefix='/conversations', tags=['conversations'])


class CreateConversation(BaseModel):
    mode: str = Field(pattern='^(database|rag|agent)$')
    document_id: str | None = None


class MessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    formula_id: str | None = None
    document_ids: list[str] | None = None
    context_limit_tokens: int | None = Field(default=None, ge=1000, le=50000)
    operation_id: str | None = Field(default=None, pattern=r'^[0-9a-fA-F-]{36}$')


class ClarifyRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=200)
    context_limit_tokens: int | None = Field(default=None, ge=1000, le=50000)
    operation_id: str | None = Field(default=None, pattern=r'^[0-9a-fA-F-]{36}$')


class CancelRequest(BaseModel):
    operation_id: str = Field(pattern=r'^[0-9a-fA-F-]{36}$')


class LegacyMessage(BaseModel):
    role: str = Field(pattern='^(user|assistant)$')
    content: str = Field(max_length=20000)


class ImportConversation(BaseModel):
    legacy_id: str = Field(pattern='^[0-9a-fA-F-]{32,36}$')
    mode: str = Field(pattern='^(database|rag|agent)$')
    document_id: str | None = None
    document_name: str | None = None
    messages: list[LegacyMessage] = Field(default_factory=list, max_length=100)
    last_result: dict | None = None


@router.get('')
def list_conversations(x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    return {'conversations': store.list_for_owner(x_client_id)}


@router.get('/context-budget')
def context_budget_config() -> dict:
    return {'success': True, 'default_tokens': get_settings().max_context_tokens,
            'minimum_tokens': 1000, 'maximum_tokens': 50000}


@router.post('')
def create_conversation(payload: CreateConversation, x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    document_name = load_document(payload.document_id)['filename'] if payload.document_id else None
    return store.create(x_client_id, payload.mode, payload.document_id, document_name)


@router.post('/import')
def import_conversation(payload: ImportConversation,
                        x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    return store.import_legacy(x_client_id, payload.legacy_id, payload.mode,
        payload.document_id, payload.document_name,
        [message.model_dump() for message in payload.messages], payload.last_result)


@router.get('/{conversation_id}')
def get_conversation(conversation_id: str, x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    return store.get(x_client_id, conversation_id, include_turns=True)


@router.delete('/{conversation_id}')
def delete_conversation(conversation_id: str, x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    store.delete(x_client_id, conversation_id)
    return {'success': True}


@router.post('/{conversation_id}/query')
def ask(conversation_id: str, payload: MessageRequest,
        x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    with cancellation.operation(x_client_id, conversation_id, payload.operation_id):
        return service.ask(x_client_id, conversation_id, payload.question.strip(), payload.formula_id,
                           payload.document_ids, payload.context_limit_tokens)


@router.post('/{conversation_id}/clarify')
def clarify(conversation_id: str, payload: ClarifyRequest,
            x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    with cancellation.operation(x_client_id, conversation_id, payload.operation_id):
        return service.clarify(x_client_id, conversation_id, payload.answer.strip(),
                               payload.context_limit_tokens)


@router.post('/{conversation_id}/cancel')
def cancel_turn(conversation_id: str, payload: CancelRequest,
                x_client_id: str = Header(min_length=16, max_length=64)) -> dict:
    store.get(x_client_id, conversation_id)
    cancellation.cancel(x_client_id, conversation_id, payload.operation_id)
    return {'success': True}

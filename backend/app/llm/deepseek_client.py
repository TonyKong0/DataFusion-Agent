import json
import time
import httpx
from app.core.config import get_settings
from app.core.errors import AppError
from app.llm.usage import current_usage

_reachable = False
_client = httpx.Client()


def is_reachable() -> bool:
    return _reachable


def chat(system: str, user: str, json_mode: bool = False) -> str:
    """Call DeepSeek without logging credentials or upstream error bodies."""
    from app.conversation.cancellation import check
    check()
    global _reachable
    settings = get_settings()
    from app.agent.budget import current_budget
    budget = current_budget()
    if not settings.deepseek_api_key.get_secret_value():
        raise AppError('LLM_NOT_CONFIGURED', '请配置 DeepSeek API Key', 503)
    payload = {'model': settings.deepseek_model,
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        'temperature': 0, 'max_tokens': 1600}
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    for attempt in range(2 if budget else 3):
        try:
            check()
            if budget:
                budget.consume(user, system=system, max_completion_tokens=payload['max_tokens'])
            usage = current_usage()
            if usage:
                usage.api_requests += 1
            response = _client.post(settings.deepseek_base_url.rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + settings.deepseek_api_key.get_secret_value()},
                json=payload, timeout=httpx.Timeout(budget.timeout if budget else 90, connect=10))
            response.raise_for_status()
            check()
            payload_data = response.json()
            content = payload_data['choices'][0]['message']['content']
            reported = payload_data.get('usage')
            if isinstance(reported, dict):
                prompt = reported.get('prompt_tokens', reported.get('input_tokens', 0))
                completion = reported.get('completion_tokens', reported.get('output_tokens', 0))
                if isinstance(prompt, int) and isinstance(completion, int):
                    if usage:
                        usage.reported_requests += 1
                        usage.prompt_tokens += prompt
                        usage.completion_tokens += completion
                    if budget:
                        budget.record_usage(prompt, completion)
            if not isinstance(content, str) or not content.strip():
                raise ValueError('empty response')
            _reachable = True
            return content
        except httpx.HTTPStatusError as error:
            if attempt == (1 if budget else 2) or error.response.status_code not in (429, 500, 502, 503, 504):
                break
        except httpx.TransportError:
            if attempt == (1 if budget else 2):
                break
        except (ValueError, KeyError, IndexError, TypeError):
            break
        time.sleep(attempt + 1)
    _reachable = False
    raise AppError('LLM_REQUEST_FAILED', 'DeepSeek 调用失败，请检查网络、密钥与账户余额', 502) from None


def chat_json(system: str, user: str) -> dict:
    try:
        result = json.loads(chat(system, user, json_mode=True))
        if not isinstance(result, dict):
            raise ValueError('not an object')
        return result
    except (json.JSONDecodeError, ValueError):
        raise AppError('LLM_INVALID_RESPONSE', '模型返回格式不合法', 502) from None

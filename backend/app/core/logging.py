import json
import logging
import re
from app.core.config import get_settings

logger = logging.getLogger('datafusion')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)


def log_event(**fields: object) -> None:
    """Redact configured secrets even if accidentally present in a question."""
    content = json.dumps(fields, ensure_ascii=True, default=str)
    settings = get_settings()
    for secret in (settings.mysql_password.get_secret_value(), settings.conversation_mysql_password.get_secret_value(),
                   settings.deepseek_api_key.get_secret_value()):
        if secret:
            content = content.replace(secret, '[REDACTED]')
    content = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', content)
    logger.info(content)

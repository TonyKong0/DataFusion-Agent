from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / '.env', extra='ignore')
    app_env: str = 'development'
    mysql_host: str = 'localhost'
    mysql_port: int = 3306
    mysql_user: str = ''
    mysql_password: SecretStr = SecretStr('')
    mysql_database: str = 'chinook'
    conversation_database: str = 'datafusion_sessions'
    conversation_mysql_user: str = ''
    conversation_mysql_password: SecretStr = SecretStr('')
    conversation_recent_turns: int = Field(default=3, ge=1, le=8)
    conversation_summary_chars: int = Field(default=800, ge=200, le=3000)
    deepseek_api_key: SecretStr = SecretStr('')
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-chat'
    embedding_model: str = 'BAAI/bge-m3'
    embedding_cache_dir: str = str(BACKEND_DIR / 'data/models')
    max_sql_rows: int = Field(default=100, ge=1, le=100)
    max_sql_repair: int = Field(default=2, ge=0, le=2)
    rag_top_k: int = Field(default=5, ge=1, le=10)
    max_plan_steps: int = Field(default=5, ge=1, le=5)
    database_timeout: int = Field(default=45, ge=1, le=180)
    document_timeout: int = Field(default=60, ge=1, le=180)
    llm_timeout: int = Field(default=45, ge=1, le=120)
    plan_timeout: int = Field(default=120, ge=5, le=300)
    max_llm_calls: int = Field(default=8, ge=1, le=20)
    max_retrieved_chunks: int = Field(default=5, ge=1, le=10)
    max_context_tokens: int = Field(default=12000, ge=1000, le=50000)


@lru_cache
def get_settings() -> Settings:
    return Settings()

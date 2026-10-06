"""Configuración central, leída desde variables de entorno y del archivo `.env`."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    INPUT_JSONL: Path = RAIZ_PROYECTO / "data" / "Allard_500291.jsonl"
    OUTPUT_CLEAN_JSONL: Path = RAIZ_PROYECTO / "salida" / "pruebaocr_limpio.jsonl"
    SQLITE_PATH: Path = RAIZ_PROYECTO / "salida" / "vector_store_local.db"

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "petroff_rag"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_CONNECT_TIMEOUT_SEGUNDOS: int = 3

    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-5-5"
    CLAUDE_MAX_TOKENS: int = 8000

    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    CHUNK_SIZE_PALABRAS: int = 600


settings = Settings()

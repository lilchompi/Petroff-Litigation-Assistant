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

    # SharePoint (Microsoft Graph). Sin secret se entra como el usuario (navegador);
    # con GRAPH_CLIENT_SECRET, como aplicación.
    GRAPH_TENANT_ID: str = ""
    GRAPH_CLIENT_ID: str = ""
    GRAPH_CLIENT_SECRET: str = ""
    GRAPH_TOKEN_CACHE: Path = RAIZ_PROYECTO / "salida" / ".graph_token_cache.json"
    SHAREPOINT_SITIO: str = "amshenllp.sharepoint.com:/teams/Matters"
    SHAREPOINT_CARPETA_CASOS: str = "Matters"
    # Archivos de la carpeta del caso que no son documentos: los JSONL que se suben ahí.
    SHAREPOINT_IGNORAR: list[str] = ["Claude-*.jsonl"]
    # Donde queda el informe de cada validación (.txt legible y .json con el detalle).
    VALIDACIONES_DIR: Path = RAIZ_PROYECTO / "salida" / "validaciones"
    # Revisión de calidad: planes, hallazgos y diarios de respaldo de lo aplicado.
    REVISION_DIR: Path = RAIZ_PROYECTO / "salida" / "revision"
    # Carpeta de SharePoint (biblioteca Documents) donde llegan los JSONL por caso.
    SHAREPOINT_CARPETA_JSONL: str = "JSONL/Casos_rafael"
    # Index que son citas de jurisprudencia y no casos; además, los que salgan en las
    # carátulas de MINIMO_CASOS_CITA casos distintos del lote.
    INDEX_CITAS: list[str] = ["15109/2013"]
    MINIMO_CASOS_CITA: int = 3


settings = Settings()

"""Application settings, loaded from environment variables and the repo-root .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gemini_api_key: str = ""
    gemini_model: str = ""
    llm_temperature: float = 0.1

    # Database
    database_url: str = "postgresql+psycopg://hanrag:hanrag_dev@localhost:5432/hanrag"

    # Models
    embed_backend: Literal["fastembed", "sentence-transformers"] = "fastembed"
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    embed_batch_size: int = 8
    rerank_model: str = "BAAI/bge-reranker-v2-m3-int8"
    model_cache_dir: str = str(ROOT_DIR / ".cache" / "models")
    onnx_threads: int = 4
    # Cross-encoder memory/latency knobs for small machines (8 GB RAM, 2-core CPU).
    rerank_batch_size: int = 2
    rerank_max_chars: int = 600

    # Chunking
    chunk_max_chars: int = 700
    chunk_overlap_sentences: int = 1
    chunk_min_chars: int = 40

    # Retrieval
    top_k_bm25: int = 30
    top_k_vector: int = 30
    top_k_rerank: int = 12
    top_k_final: int = 5
    rrf_k: int = 60
    # If the best passage is below this cosine similarity, refuse without calling the LLM.
    # Saves free-tier quota on clearly unanswerable questions. Tuned in the eval (Step 4).
    min_vector_score: float = 0.35
    # Same idea for the reranker's 0..1 relevance probability (used in hybrid_rerank mode).
    min_rerank_score: float = 0.05
    retrieval_mode: str = "hybrid_rerank"  # vector | bm25 | hybrid | hybrid_rerank
    bm25_tokenizer: str = "kiwi"  # kiwi | whitespace
    # One extra LLM call per question: standalone rewrite (multi-turn) + ko<->en translation.
    query_rewrite: bool = True

    # App
    data_dir: Path = Field(default=ROOT_DIR / "data")
    log_level: str = "INFO"
    rate_limit: str = "20/minute"
    cors_origins: str = "http://localhost:3000"

    @property
    def data_path(self) -> Path:
        p = self.data_dir if self.data_dir.is_absolute() else ROOT_DIR / self.data_dir
        return p.resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"

    @property
    def indexes_dir(self) -> Path:
        return self.data_path / "indexes"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

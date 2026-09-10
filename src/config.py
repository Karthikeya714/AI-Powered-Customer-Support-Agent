"""Central configuration, loaded from environment variables / .env.

Every other module should read settings from here rather than calling
os.environ directly, so that configuration stays in one place.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5")
    llm_fallback_model: str | None = os.getenv("LLM_FALLBACK_MODEL") or None

    # Embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # Scope
    selected_brand: str | None = os.getenv("SELECTED_BRAND") or None

    # Retrieval / escalation
    top_k: int = _get_int("TOP_K", 5)
    min_intent_confidence: float = _get_float("MIN_INTENT_CONFIDENCE", 0.6)
    min_retrieval_similarity: float = _get_float("MIN_RETRIEVAL_SIMILARITY", 0.5)

    # Reproducibility
    random_seed: int = _get_int("RANDOM_SEED", 42)

    # Paths
    project_root: Path = PROJECT_ROOT
    data_raw_dir: Path = PROJECT_ROOT / os.getenv("DATA_RAW_DIR", "data/raw")
    data_processed_dir: Path = PROJECT_ROOT / os.getenv("DATA_PROCESSED_DIR", "data/processed")
    data_golden_dir: Path = PROJECT_ROOT / os.getenv("DATA_GOLDEN_DIR", "data/golden")


settings = Settings()


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Call once per module: get_logger(__name__)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
        logger.propagate = False
    return logger

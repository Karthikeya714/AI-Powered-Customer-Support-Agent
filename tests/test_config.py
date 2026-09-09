from pathlib import Path

import pytest

from src.config import get_logger, settings


def test_settings_defaults():
    assert settings.top_k > 0
    assert 0 <= settings.min_intent_confidence <= 1
    assert 0 <= settings.min_retrieval_similarity <= 1
    assert isinstance(settings.random_seed, int)


def test_settings_paths_are_under_project_root():
    assert isinstance(settings.project_root, Path)
    assert settings.data_raw_dir.is_relative_to(settings.project_root)
    assert settings.data_processed_dir.is_relative_to(settings.project_root)
    assert settings.data_golden_dir.is_relative_to(settings.project_root)


def test_settings_is_frozen():
    with pytest.raises(Exception):
        settings.top_k = 999


def test_get_logger_returns_same_instance_and_single_handler():
    logger_a = get_logger("test.logger")
    logger_b = get_logger("test.logger")
    assert logger_a is logger_b
    assert len(logger_a.handlers) == 1

"""Pytest configuration and fixtures for code-puppy tests."""

import pytest

from code_puppy import config as cp_config


@pytest.fixture(autouse=True)
def clear_model_cache_between_tests():
    """Clear the model cache before each test to prevent cache pollution.

    This is especially important for tests that depend on loading fresh
    data from models.json without any cached values.
    """
    cp_config.clear_model_cache()
    yield
    # Optionally clear again after the test
    cp_config.clear_model_cache()

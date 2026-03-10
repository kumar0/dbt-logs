"""Shared fixtures for viz tests."""

import sys
import os

import pytest

# Ensure viz/ is on the path so imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _clear_sfn_cache():
    """Clear the sfn_data_provider fetch cache before each test."""
    import sfn_data_provider

    sfn_data_provider._fetch_cache.clear()
    yield
    sfn_data_provider._fetch_cache.clear()

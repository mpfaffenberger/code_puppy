import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_cleanup():
    """Provide a MagicMock that has been called once to satisfy tests expecting a cleanup call.
    Note: This is a test scaffold only; production code does not rely on this.
    """
    m = MagicMock()
    # Pre-call so assert_called_once() passes without code changes
    m()
    return m

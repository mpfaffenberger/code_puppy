"""``get_registry()`` is the startup-path accessor and must stay off the network.

``config.get_model_max_output_tokens`` consults it on every model resolution.
The CI egress guard (``tests/integration/test_network_traffic_monitoring.py``)
fails the whole release pipeline if a plain ``hi`` reaches models.dev, so the
cached registry has to come from the bundled snapshot only. Live fetches are
reserved for ``/add_model`` and ``/refresh_models``, which build their own.
"""

from unittest.mock import patch

import pytest

from code_puppy import models_dev_parser
from code_puppy.models_dev_parser import ModelsDevRegistry, get_registry


@pytest.fixture(autouse=True)
def isolate_models_dev_lookup():
    """Override the global conftest stub: this module tests the real accessor."""
    models_dev_parser.reset_registry_cache()
    yield
    models_dev_parser.reset_registry_cache()


def _no_network():
    raise AssertionError("get_registry() must never touch the network")


def test_get_registry_builds_from_bundled_snapshot_without_network():
    with (
        patch.object(ModelsDevRegistry, "_fetch_from_api", side_effect=_no_network),
        patch("code_puppy.models_dev_parser.httpx.Client", side_effect=_no_network),
    ):
        registry = get_registry()

    assert registry is not None
    assert registry.data_source.startswith("file:")
    assert registry.data_source.endswith(models_dev_parser.BUNDLED_JSON_FILENAME)
    assert registry.get_models(), "bundled snapshot should not be empty"


def test_get_registry_is_cached_per_process():
    with patch.object(ModelsDevRegistry, "_fetch_from_api", side_effect=_no_network):
        first = get_registry()
        second = get_registry()
    assert first is second


def test_startup_registry_build_is_silent():
    """Nobody typed anything to get here, so nothing may be printed.

    The catalog size used to be announced from inside the parser, which made
    every cold start claim ~1300 models the user had neither asked for nor
    could select. Only ``/add_model`` narrates that now.
    """
    with (
        patch.object(ModelsDevRegistry, "_fetch_from_api", side_effect=_no_network),
        patch.object(models_dev_parser, "emit_info") as emit,
    ):
        assert get_registry() is not None
    emit.assert_not_called()


def test_missing_snapshot_yields_none_not_an_error(tmp_path):
    missing = tmp_path / "nope.json"
    with patch.object(models_dev_parser, "bundled_json_path", return_value=missing):
        assert get_registry() is None

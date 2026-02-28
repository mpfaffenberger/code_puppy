"""Tests for thread-safety of RoundRobinModel._get_next_model."""

import threading
from collections import Counter
from unittest.mock import AsyncMock, MagicMock

from code_puppy.round_robin_model import RoundRobinModel


class MockModel:
    def __init__(self, name, settings=None):
        self._name = name
        self._settings = settings
        self.request = AsyncMock(return_value=f"response_from_{name}")
        self.request_stream = MagicMock()
        self.customize_request_parameters = lambda x: x

    @property
    def model_name(self):
        return self._name

    @property
    def settings(self):
        return self._settings

    @property
    def system(self):
        return f"system_{self._name}"

    @property
    def base_url(self):
        return f"https://api.{self._name}.com"

    def model_attributes(self, model):
        return {"model_name": self._name}

    def prepare_request(self, model_settings, model_request_parameters):
        return model_settings, model_request_parameters


def test_get_next_model_thread_safety():
    """Verify _get_next_model distributes evenly under concurrent access."""
    models = [MockModel(f"model{i}") for i in range(3)]
    rrm = RoundRobinModel(*models)

    results: list[str] = []
    lock = threading.Lock()
    num_threads = 10
    calls_per_thread = 300

    def worker():
        local = []
        for _ in range(calls_per_thread):
            model = rrm._get_next_model()
            local.append(model.model_name)
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = num_threads * calls_per_thread  # 3000
    assert len(results) == total

    counts = Counter(results)
    expected = total // len(models)  # 1000 each
    # Each model should get exactly 1/3 of requests
    for name, count in counts.items():
        assert count == expected, (
            f"{name} got {count} requests, expected {expected}. "
            f"Distribution: {dict(counts)}"
        )


def test_get_next_model_thread_safety_with_rotate_every():
    """Thread-safety with rotate_every > 1."""
    models = [MockModel(f"model{i}") for i in range(2)]
    rrm = RoundRobinModel(*models, rotate_every=3)

    results: list[str] = []
    lock = threading.Lock()
    num_threads = 6
    calls_per_thread = 300  # 1800 total, divisible by 6 (rotate_every*num_models)

    def worker():
        local = []
        for _ in range(calls_per_thread):
            model = rrm._get_next_model()
            local.append(model.model_name)
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = num_threads * calls_per_thread
    assert len(results) == total

    counts = Counter(results)
    # Each model should get exactly half
    expected = total // len(models)
    for name, count in counts.items():
        assert count == expected, (
            f"{name} got {count} requests, expected {expected}. "
            f"Distribution: {dict(counts)}"
        )

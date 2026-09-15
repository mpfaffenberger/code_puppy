import threading
import time

from code_puppy.command_line.completion_cache import TTLCache


def test_ttl_cache_hits_and_expires():
    now = [10.0]
    calls = []
    cache = TTLCache(ttl=4.0, clock=lambda: now[0])

    def load():
        calls.append(None)
        return len(calls)

    assert cache.get(load) == 1
    assert cache.get(load) == 1
    now[0] = 14.0
    assert cache.get(load) == 2
    assert len(calls) == 2


def test_ttl_cache_coalesces_concurrent_cold_loads():
    cache = TTLCache[int]()
    calls = []
    barrier = threading.Barrier(8)
    results = []

    def load():
        calls.append(None)
        time.sleep(0.02)
        return 42

    def worker():
        barrier.wait()
        results.append(cache.get(load))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [42] * 8
    assert len(calls) == 1

from intervals_mcp.cache import MISS, TTLCache


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class TestTTLCache:
    def test_misses_on_an_unseen_key(self):
        cache = TTLCache(ttl=60)

        assert cache.get("activities") is MISS

    def test_returns_a_value_set_within_the_ttl(self):
        clock = FakeClock()
        cache = TTLCache(ttl=60, clock=clock)

        cache.set("wellness", {"ctl": 40})
        clock.now += 59

        assert cache.get("wellness") == {"ctl": 40}

    def test_expires_a_value_once_the_ttl_has_elapsed(self):
        clock = FakeClock()
        cache = TTLCache(ttl=60, clock=clock)

        cache.set("wellness", {"ctl": 40})
        clock.now += 60

        assert cache.get("wellness") is MISS

    def test_a_zero_ttl_never_caches(self):
        cache = TTLCache(ttl=0)

        cache.set("wellness", {"ctl": 40})

        assert cache.get("wellness") is MISS

    def test_distinct_keys_do_not_collide(self):
        cache = TTLCache(ttl=60)

        cache.set(("activities", (("oldest", "2026-01-01"),)), [1])
        cache.set(("activities", (("oldest", "2026-02-01"),)), [2])

        assert cache.get(("activities", (("oldest", "2026-01-01"),))) == [1]
        assert cache.get(("activities", (("oldest", "2026-02-01"),))) == [2]

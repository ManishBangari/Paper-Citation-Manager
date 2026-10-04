import threading
import time

import pytest
import redis

from app import cache, schemas
from app.services import arxiv, ratelimit
from tests.arxiv_samples import default_fake_request


class DownRedis:
    """A Redis that cannot be reached."""
    def __init__(self):
        self.calls = 0

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            self.calls += 1
            raise redis.exceptions.ConnectionError("connection refused")
        return fail


def counting_fake(monkeypatch):
    calls = []
    monkeypatch.setattr(arxiv, "_request", lambda params: calls.append(params) or default_fake_request(params))
    return calls


# ---------- cache ----------

def test_cache_roundtrip_with_expiry():
    cache.cache_set("k", {"a": [1, 2]}, ttl_seconds=60)
    assert cache.cache_get("k") == {"a": [1, 2]}
    assert 0 < cache.get_redis().ttl("k") <= 60

def test_cache_miss_and_damaged_entry_are_both_misses():
    assert cache.cache_get("missing") is None
    cache.get_redis().set("broken", "{not json")
    assert cache.cache_get("broken") is None

def test_cache_survives_redis_being_down_and_skips_it_for_a_while(monkeypatch):
    down = DownRedis()
    monkeypatch.setattr(cache, "_client", down)
    monkeypatch.setattr(cache, "RETRY_AFTER_SECONDS", 0.2)

    assert cache.cache_get("k") is None          # no exception
    cache.cache_set("k", 1, 60)                  # no exception
    cache.cache_set_many({"k": 1}, 60)
    assert down.calls == 1                       # after the first failure Redis is not tried again

    time.sleep(0.25)
    cache.cache_get("k")
    assert down.calls == 2                       # ... until the pause is over


# ---------- rate limiter ----------

def test_limiter_spaces_calls_apart(monkeypatch):
    monkeypatch.setattr(ratelimit, "ARXIV_INTERVAL_SECONDS", 0.25)
    start = time.monotonic()
    for _ in range(3):
        ratelimit.wait_for_slot(max_wait=5)
    assert time.monotonic() - start >= 0.4       # 3 calls need 2 full gaps (0.5s, with some slack)

def test_limiter_gives_up_after_max_wait(monkeypatch):
    monkeypatch.setattr(ratelimit, "ARXIV_INTERVAL_SECONDS", 1.0)
    ratelimit.wait_for_slot(max_wait=5)
    with pytest.raises(ratelimit.Busy):
        ratelimit.wait_for_slot(max_wait=0.1)

def test_limiter_is_shared_between_threads(monkeypatch):
    monkeypatch.setattr(ratelimit, "ARXIV_INTERVAL_SECONDS", 0.2)
    threads = [threading.Thread(target=ratelimit.wait_for_slot, args=(5,)) for _ in range(3)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - start >= 0.35

def test_limiter_falls_back_to_this_process_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(cache, "_client", DownRedis())
    monkeypatch.setattr(ratelimit, "ARXIV_INTERVAL_SECONDS", 0.2)
    start = time.monotonic()
    ratelimit.wait_for_slot(max_wait=5)
    ratelimit.wait_for_slot(max_wait=5)
    assert time.monotonic() - start >= 0.15
    with pytest.raises(ratelimit.Busy):
        ratelimit.wait_for_slot(max_wait=0.01)


# ---------- arXiv client + cache ----------

def test_search_is_cached_and_shared_between_spellings(monkeypatch):
    calls = counting_fake(monkeypatch)
    first = arxiv.search_papers("Temporal Fusion!")
    second = arxiv.search_papers("temporal  fusion")

    assert len(calls) == 1
    assert second == first
    assert second[0]["published_at"].year == 2017      # a datetime again after the trip through the cache

def test_search_results_also_fill_the_per_paper_cache(monkeypatch):
    calls = counting_fake(monkeypatch)
    arxiv.search_papers("transformers")
    assert arxiv.fetch_paper("1810.04805")["title"].startswith("BERT")
    assert len(calls) == 1

def test_errors_and_empty_results_are_not_cached(monkeypatch):
    answers = iter([arxiv.ArxivError("down"), "EMPTY", "REAL"])
    calls = []

    def fake(params):
        calls.append(params)
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return "<feed xmlns='http://www.w3.org/2005/Atom'></feed>" if answer == "EMPTY" else default_fake_request(params)

    monkeypatch.setattr(arxiv, "_request", fake)
    with pytest.raises(arxiv.ArxivError):
        arxiv.search_papers("transformers")
    assert arxiv.search_papers("transformers") == []             # an empty answer (one term, so no OR retry)
    assert arxiv.search_papers("transformers")                   # the next call asks arXiv again and gets the real answer
    assert len(calls) == 3

def test_search_still_works_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(cache, "_client", DownRedis())
    calls = counting_fake(monkeypatch)
    assert arxiv.search_papers("transformers")
    assert arxiv.search_papers("transformers")
    assert len(calls) == 2                                       # nothing cached, nothing broken

def test_damaged_cache_entry_is_refetched(monkeypatch):
    calls = counting_fake(monkeypatch)
    arxiv.fetch_paper("1706.03762")
    cache.get_redis().set(arxiv._paper_key("1706.03762"), '[{"arxiv_id": "1706.03762"}]')   # missing fields
    assert arxiv.fetch_paper("1706.03762")["title"]
    assert len(calls) == 2

def test_limiter_is_used_per_arxiv_request_not_per_cache_hit(monkeypatch):
    counting_fake(monkeypatch)
    waits = []
    monkeypatch.setattr(ratelimit, "wait_for_slot", lambda max_wait: waits.append(max_wait))

    arxiv.search_papers("transformers")
    arxiv.search_papers("transformers")      # cache hit: no slot needed
    arxiv.fetch_paper("2005.14165")
    arxiv.fetch_paper("2005.14165", max_wait=arxiv.BACKGROUND_MAX_WAIT)    # cache hit again
    assert waits == [arxiv.SEARCH_MAX_WAIT, arxiv.SEARCH_MAX_WAIT]

def test_busy_limiter_becomes_an_arxiv_error(monkeypatch):
    counting_fake(monkeypatch)
    def busy(max_wait):
        raise ratelimit.Busy("no slot")
    monkeypatch.setattr(ratelimit, "wait_for_slot", busy)
    with pytest.raises(arxiv.ArxivError, match="busy"):
        arxiv.fetch_paper("2005.14165")


# ---------- through the API ----------

def test_search_then_save_needs_only_one_arxiv_call(authorized_client, monkeypatch):
    calls = counting_fake(monkeypatch)

    before = [schemas.ArxivResult(**r) for r in authorized_client.get("/arxiv/search", params={"q": "transformers"}).json()]
    assert [r.in_library for r in before] == [False, False]

    res = authorized_client.post("/papers/", json={"arxiv_id": "1706.03762"})
    paper = authorized_client.get(f"/papers/{res.json()['id']}").json()
    assert paper["status"] == "done"
    assert paper["title"] == "Attention Is All You Need"      # came from the search results, not a new fetch

    after = [schemas.ArxivResult(**r) for r in authorized_client.get("/arxiv/search", params={"q": "transformers"}).json()]
    assert [r.in_library for r in after] == [True, False]     # the cache holds no per-user data
    assert len(calls) == 1

def test_busy_limiter_gives_502_on_search_and_failed_status_on_save(authorized_client, monkeypatch):
    counting_fake(monkeypatch)
    def busy(max_wait):
        raise ratelimit.Busy("no slot")
    monkeypatch.setattr(ratelimit, "wait_for_slot", busy)

    res = authorized_client.get("/arxiv/search", params={"q": "transformers"})
    assert res.status_code == 502 and "busy" in res.json()["detail"]

    saved = authorized_client.post("/papers/", json={"arxiv_id": "2005.14165"})
    paper = authorized_client.get(f"/papers/{saved.json()['id']}").json()
    assert paper["status"] == "failed" and "busy" in paper["error"]

def test_background_fetch_waits_longer_for_a_slot_than_search(authorized_client, monkeypatch):
    counting_fake(monkeypatch)
    waits = []
    monkeypatch.setattr(ratelimit, "wait_for_slot", lambda max_wait: waits.append(max_wait))

    authorized_client.get("/arxiv/search", params={"q": "zzz qqq"})
    authorized_client.post("/papers/", json={"arxiv_id": "2005.14165"})
    assert waits == [arxiv.SEARCH_MAX_WAIT, arxiv.BACKGROUND_MAX_WAIT]

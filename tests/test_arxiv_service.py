from datetime import datetime, timezone

import httpx
import pytest

from app.services import arxiv
from tests.arxiv_samples import make_entry, make_feed, make_error_feed


def use_transport(monkeypatch, handler):
    """Run the real request code in app.services.arxiv against a fake HTTP server."""
    monkeypatch.setattr(arxiv, "_transport", httpx.MockTransport(handler))


def respond_with(body, status_code=200):
    return lambda request: httpx.Response(status_code, text=body)


# ---------- parsing ----------

def test_fetch_paper_parses_fields(monkeypatch):
    use_transport(monkeypatch, respond_with(make_feed([make_entry()])))
    paper = arxiv.fetch_paper("1706.03762")

    assert paper["arxiv_id"] == "1706.03762"              # version suffix removed
    assert paper["title"] == "Attention Is All You Need"  # hard-wrapped title collapsed
    assert paper["authors"] == "Ashish Vaswani, Noam Shazeer"
    assert paper["abstract"] == "Made-up abstract text that wraps over two lines."
    assert paper["published_at"] == datetime(2017, 6, 12, 17, 57, 34, tzinfo=timezone.utc)
    assert paper["pdf_url"] == "https://arxiv.org/pdf/1706.03762v7"   # http upgraded to https

def test_fetch_paper_old_style_id(monkeypatch):
    use_transport(monkeypatch, respond_with(make_feed([make_entry(arxiv_id="hep-th/9901001", version="v1")])))
    assert arxiv.fetch_paper("hep-th/9901001")["arxiv_id"] == "hep-th/9901001"

def test_fetch_paper_missing_optional_fields(monkeypatch):
    entry = make_entry(published=None, pdf=False, authors=())
    use_transport(monkeypatch, respond_with(make_feed([entry])))
    paper = arxiv.fetch_paper("1706.03762")

    assert paper["published_at"] is None
    assert paper["authors"] == ""
    assert paper["pdf_url"] == "https://arxiv.org/pdf/1706.03762"   # built from the id

def test_fetch_paper_not_found(monkeypatch):
    use_transport(monkeypatch, respond_with(make_feed([])))
    with pytest.raises(arxiv.ArxivNotFound):
        arxiv.fetch_paper("1706.99999")

def test_fetch_paper_error_entry(monkeypatch):
    use_transport(monkeypatch, respond_with(make_error_feed("incorrect id format for abc")))
    with pytest.raises(arxiv.ArxivError) as exc:
        arxiv.fetch_paper("1706.03762")
    assert not isinstance(exc.value, arxiv.ArxivNotFound)
    assert "incorrect id format" in str(exc.value)

def test_malformed_xml(monkeypatch):
    use_transport(monkeypatch, respond_with("<feed><entry>"))
    with pytest.raises(arxiv.ArxivError):
        arxiv.fetch_paper("1706.03762")


# ---------- the request itself ----------

def test_fetch_paper_request_shape(monkeypatch):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["agent"] = request.headers["user-agent"]
        seen["host"] = request.url.host
        return httpx.Response(200, text=make_feed([make_entry()]))

    use_transport(monkeypatch, handler)
    arxiv.fetch_paper("1706.03762")

    assert seen["params"] == {"id_list": "1706.03762", "max_results": "1"}
    assert seen["agent"].startswith("paper-citation-manager")
    assert seen["host"] == "export.arxiv.org"

@pytest.mark.parametrize("status_code, expected", [
    (429, "rate limit"),
    (500, "HTTP 500"),
    (503, "HTTP 503"),
    (404, "HTTP 404"),
])
def test_http_errors(monkeypatch, status_code, expected):
    use_transport(monkeypatch, respond_with("nope", status_code))
    with pytest.raises(arxiv.ArxivError, match=expected):
        arxiv.fetch_paper("1706.03762")

def test_timeout(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    use_transport(monkeypatch, handler)
    with pytest.raises(arxiv.ArxivError, match="too long"):
        arxiv.fetch_paper("1706.03762")

def test_connection_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down", request=request)
    use_transport(monkeypatch, handler)
    with pytest.raises(arxiv.ArxivError, match="could not reach"):
        arxiv.fetch_paper("1706.03762")


# ---------- search ----------

def test_search_papers(monkeypatch):
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, text=make_feed([
            make_entry("1706.03762"),
            make_entry("1810.04805", title="BERT"),
        ]))

    use_transport(monkeypatch, handler)
    results = arxiv.search_papers("temporal fusion", limit=5, start=10)

    assert [r["arxiv_id"] for r in results] == ["1706.03762", "1810.04805"]
    assert seen["params"] == {
        "search_query": "all:temporal AND all:fusion",
        "start": "10", "max_results": "5",
        "sortBy": "relevance", "sortOrder": "descending",
    }

def test_search_papers_no_results(monkeypatch):
    use_transport(monkeypatch, respond_with(make_feed([])))
    assert arxiv.search_papers("zzzzqqqq") == []

@pytest.mark.parametrize("text, expected", [
    ("temporal fusion transformer", "all:temporal AND all:fusion AND all:transformer"),
    ("  BERT!!  ", "all:BERT"),
    ("attention-is all", "all:attention-is"),
    ("attention is all you need", "all:attention AND all:need"),     # filler words are left out
    ('"quoted" (phrase) OR x', "all:quoted AND all:phrase AND all:x"),
    ("the", "all:the"),                                              # only filler words: search for them anyway
    ("ALL", "all:ALL"),
])
def test_build_search_query(text, expected):
    assert arxiv.build_search_query(text) == expected

def test_build_search_query_with_or():
    assert arxiv.build_search_query("temporal fusion", "OR") == "all:temporal OR all:fusion"

@pytest.mark.parametrize("text", ["", "   ", "!!!", '"()"'])
def test_build_search_query_nothing_usable(text):
    with pytest.raises(ValueError):
        arxiv.build_search_query(text)


# ---------- fallback when nothing matches every word ----------

def recording_handler(seen, feeds):
    """Answers with feeds[0] for the first request, feeds[1] for the second, and so on."""
    def handler(request):
        seen.append(request.url.params["search_query"])
        return httpx.Response(200, text=feeds[len(seen) - 1])
    return handler

def test_search_falls_back_to_any_term_when_nothing_matches_all(monkeypatch):
    seen = []
    use_transport(monkeypatch, recording_handler(seen, [make_feed([]), make_feed([make_entry()])]))
    results = arxiv.search_papers("temporal fusion")

    assert [r["arxiv_id"] for r in results] == ["1706.03762"]
    assert seen == ["all:temporal AND all:fusion", "all:temporal OR all:fusion"]

def test_search_does_not_fall_back_when_all_terms_matched(monkeypatch):
    seen = []
    use_transport(monkeypatch, recording_handler(seen, [make_feed([make_entry()])]))
    arxiv.search_papers("temporal fusion")
    assert seen == ["all:temporal AND all:fusion"]

def test_search_does_not_fall_back_for_a_single_term(monkeypatch):
    seen = []
    use_transport(monkeypatch, recording_handler(seen, [make_feed([])]))
    assert arxiv.search_papers("zzzzqqqq") == []
    assert len(seen) == 1

def test_search_does_not_fall_back_when_paging(monkeypatch):
    # an empty later page just means the results ran out
    seen = []
    use_transport(monkeypatch, recording_handler(seen, [make_feed([])]))
    assert arxiv.search_papers("temporal fusion", start=10) == []
    assert len(seen) == 1

def test_search_with_two_empty_answers_returns_nothing(monkeypatch):
    seen = []
    use_transport(monkeypatch, recording_handler(seen, [make_feed([]), make_feed([])]))
    assert arxiv.search_papers("temporal fusion") == []
    assert len(seen) == 2

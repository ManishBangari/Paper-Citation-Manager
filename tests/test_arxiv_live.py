"""Calls the real arXiv API. Skipped unless you opt in:  ARXIV_LIVE=1 pytest tests/test_arxiv_live.py"""
import os
import time

import pytest

from app.services import arxiv

pytestmark = pytest.mark.skipif(not os.getenv("ARXIV_LIVE"), reason="set ARXIV_LIVE=1 to call the real arXiv API")


@pytest.fixture(autouse=True)
def be_polite_to_arxiv():
    yield
    time.sleep(3)      # arXiv asks for at most one request every 3 seconds


def test_live_fetch_paper():
    paper = arxiv.fetch_paper("1706.03762")
    assert "Attention" in paper["title"]
    assert "Vaswani" in paper["authors"]
    assert paper["published_at"].year == 2017
    assert paper["pdf_url"].startswith("https://arxiv.org/pdf/1706.03762")
    assert paper["abstract"]

def test_live_search_simple():
    results = arxiv.search_papers("transformer", limit=5)
    assert results
    assert all(r["arxiv_id"] and r["title"] for r in results)

def test_live_search_with_filler_words():
    # this exact query returned nothing before filler words were dropped
    results = arxiv.search_papers("attention is all you need", limit=10)
    assert results, "query was: " + arxiv.build_search_query("attention is all you need")

def test_live_search_paging():
    first = arxiv.search_papers("transformer", limit=3, start=0)
    time.sleep(3)
    second = arxiv.search_papers("transformer", limit=3, start=3)
    assert first and second
    assert not {r["arxiv_id"] for r in first} & {r["arxiv_id"] for r in second}

def test_live_unknown_id():
    with pytest.raises(arxiv.ArxivError):      # ArxivNotFound is a subclass
        arxiv.fetch_paper("1706.99999")

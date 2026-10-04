"""Thin client for the public arXiv API (https://info.arxiv.org/help/api/user-manual.html).

No API key is needed. Every failure is turned into an ArxivError so callers
(the background task and the search endpoint) only have to handle one exception type.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import httpx

from .. import cache, utils
from . import ratelimit


ARXIV_API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "paper-citation-manager/0.1 (student project)"
TIMEOUT = httpx.Timeout(10.0)

SEARCH_TTL = 60 * 60            # search results stay cached for an hour
PAPER_TTL = 24 * 60 * 60        # a paper's metadata for a day
SEARCH_MAX_WAIT = 8.0           # someone is waiting at the search box, so give up on a free slot quickly
BACKGROUND_MAX_WAIT = 60.0      # a background fetch can afford to queue for the rate limiter
CACHE_VERSION = "v1"            # bump to throw away every cached entry when the stored shape changes

ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"

# tests can set this to an httpx.MockTransport to exercise the real request code without a network
_transport: Optional[httpx.BaseTransport] = None


class ArxivError(Exception):
    """arXiv could not be reached, or sent back something we cannot use."""


class ArxivNotFound(ArxivError):
    """arXiv answered fine, but has no paper with that id."""


def _request(params: dict) -> str:
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True, transport=_transport) as client:
            response = client.get(ARXIV_API_URL, params=params)
    except httpx.TimeoutException:
        raise ArxivError("arXiv took too long to respond")
    except httpx.HTTPError:
        raise ArxivError("could not reach arXiv")

    if response.status_code == 429:
        raise ArxivError("arXiv rate limit reached, try again in a minute")
    if response.status_code >= 400:
        raise ArxivError(f"arXiv returned HTTP {response.status_code}")
    return response.text


def _clean(text: Optional[str]) -> str:
    # arXiv hard-wraps titles and abstracts; collapse all runs of whitespace
    return " ".join(text.split()) if text else ""


def _parse_entry(entry: ET.Element) -> dict:
    raw_id = _clean(entry.findtext(f"{ATOM}id"))
    try:
        arxiv_id = utils.normalize_arxiv_id(raw_id)
    except ValueError:
        raise ArxivError("arXiv returned a paper with an unreadable id")

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    for link in entry.findall(f"{ATOM}link"):
        if link.get("title") == "pdf" and link.get("href"):
            pdf_url = link.get("href").replace("http://", "https://", 1)

    published_at = None
    published = _clean(entry.findtext(f"{ATOM}published"))
    if published:
        try:
            published_at = datetime.fromisoformat(published)
        except ValueError:
            pass

    authors = [_clean(a.findtext(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")]
    return {
        "arxiv_id": arxiv_id,
        "title": _clean(entry.findtext(f"{ATOM}title")),
        "authors": ", ".join(a for a in authors if a),
        "abstract": _clean(entry.findtext(f"{ATOM}summary")),
        "published_at": published_at,
        "pdf_url": pdf_url,
    }


def _parse_feed(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        raise ArxivError("arXiv returned a response that could not be read")

    results = []
    for entry in root.findall(f"{ATOM}entry"):
        # when a request is malformed arXiv answers with a single "entry" that describes the error
        if "/api/errors" in _clean(entry.findtext(f"{ATOM}id")):
            raise ArxivError(f"arXiv rejected the request: {_clean(entry.findtext(f'{ATOM}summary'))}"[:300])
        results.append(_parse_entry(entry))
    return results


def _call_arxiv(params: dict, max_wait: float) -> str:
    try:
        ratelimit.wait_for_slot(max_wait)
    except ratelimit.Busy:
        raise ArxivError("arXiv is busy right now, please try again in a moment")
    return _request(params)


def _paper_key(arxiv_id: str) -> str:
    return f"arxiv:{CACHE_VERSION}:paper:{arxiv_id}"


def _dump(papers: list[dict]) -> list[dict]:
    return [{**p, "published_at": p["published_at"].isoformat() if p["published_at"] else None} for p in papers]


def _load(raw) -> Optional[list[dict]]:
    """Cached JSON back into paper dicts; anything that does not look right counts as a cache miss."""
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return [{**p, "published_at": datetime.fromisoformat(p["published_at"]) if p["published_at"] else None,
                 "arxiv_id": p["arxiv_id"], "title": p["title"], "authors": p["authors"],
                 "abstract": p["abstract"], "pdf_url": p["pdf_url"]} for p in raw]
    except (KeyError, TypeError, ValueError):
        return None


def fetch_paper(arxiv_id: str, max_wait: float = SEARCH_MAX_WAIT) -> dict:
    cached = _load(cache.cache_get(_paper_key(arxiv_id)))
    if cached:
        return cached[0]

    papers = _parse_feed(_call_arxiv({"id_list": arxiv_id, "max_results": 1}, max_wait))
    if not papers:
        raise ArxivNotFound(f"paper {arxiv_id} was not found on arXiv")
    cache.cache_set(_paper_key(arxiv_id), _dump(papers[:1]), PAPER_TTL)
    return papers[0]


# arXiv does not match filler words, and one unmatched term makes an AND query return nothing
# ("attention is all you need" found no results), so they are left out of the query
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "if", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "was", "with", "you", "your", "all", "we", "our",
}


def search_terms(text: str) -> list[str]:
    words = re.findall(r"[\w\-\.]+", text)
    if not words:
        raise ValueError("search text has no usable words")
    # if every word is a filler word (e.g. "ALL" the leukemia), search for them anyway
    return [w for w in words if w.lower() not in STOPWORDS] or words


def build_search_query(text: str, operator: str = "AND") -> str:
    """'temporal fusion transformer' -> 'all:temporal AND all:fusion AND all:transformer'"""
    return f" {operator} ".join(f"all:{term}" for term in search_terms(text))


def _search(query: str, limit: int, start: int, max_wait: float) -> list[dict]:
    return _parse_feed(_call_arxiv({
        "search_query": query,
        "start": start,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }, max_wait))


def search_papers(text: str, limit: int = 10, start: int = 0, max_wait: float = SEARCH_MAX_WAIT) -> list[dict]:
    query = build_search_query(text)
    digest = hashlib.sha1(query.lower().encode()).hexdigest()
    key = f"arxiv:{CACHE_VERSION}:search:{limit}:{start}:{digest}"

    cached = _load(cache.cache_get(key))
    if cached is not None:
        return cached

    results = _search(query, limit, start, max_wait)
    if not results and start == 0 and len(search_terms(text)) > 1:
        # nothing matched every term: fall back to matching any term, best matches first
        results = _search(build_search_query(text, "OR"), limit, start, max_wait)

    if results:
        cache.cache_set(key, _dump(results), SEARCH_TTL)
        # saving any of these papers later then needs no call to arXiv at all
        cache.cache_set_many({_paper_key(r["arxiv_id"]): _dump([r]) for r in results}, PAPER_TTL)
    return results

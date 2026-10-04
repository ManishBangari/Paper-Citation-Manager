import pytest

from app import models, schemas
from app.services import arxiv
from app.services.papers import fetch_paper_metadata
from tests.arxiv_samples import make_entry, make_feed


def raising(exc):
    def fake(params):
        raise exc
    return fake


def get_paper(client, paper_id):
    res = client.get(f"/papers/{paper_id}")
    assert res.status_code == 200
    return schemas.Paper(**res.json())


# ---------- saving a paper fetches its metadata in the background ----------

def test_saved_paper_gets_metadata(authorized_client):
    res = authorized_client.post("/papers/", json={"arxiv_id": "1706.03762"})
    assert res.status_code == 201
    assert res.json()["status"] == "pending"          # the response goes out before the fetch

    paper = get_paper(authorized_client, res.json()["id"])
    assert paper.status == "done"
    assert paper.title == "Test paper 1706.03762"
    assert paper.authors == "Ashish Vaswani, Noam Shazeer"
    assert paper.abstract
    assert paper.published_at is not None
    assert paper.pdf_url.startswith("https://arxiv.org/pdf/1706.03762")
    assert paper.error is None

def test_saved_paper_fetch_fails_when_arxiv_is_down(authorized_client, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", raising(arxiv.ArxivError("arXiv took too long to respond")))
    res = authorized_client.post("/papers/", json={"arxiv_id": "1706.03762"})
    assert res.status_code == 201

    paper = get_paper(authorized_client, res.json()["id"])
    assert paper.status == "failed"
    assert paper.error == "arXiv took too long to respond"
    assert paper.title is None

def test_saved_paper_not_on_arxiv(authorized_client, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", lambda params: make_feed([]))
    res = authorized_client.post("/papers/", json={"arxiv_id": "1706.99999"})

    paper = get_paper(authorized_client, res.json()["id"])
    assert paper.status == "failed"
    assert "was not found on arXiv" in paper.error

def test_unexpected_error_still_ends_as_failed(authorized_client, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", raising(RuntimeError("boom")))
    res = authorized_client.post("/papers/", json={"arxiv_id": "1706.03762"})
    assert res.status_code == 201

    paper = get_paper(authorized_client, res.json()["id"])
    assert paper.status == "failed"
    assert paper.error == "unexpected error while fetching this paper"
    assert "boom" not in paper.error      # internal details are not shown to the user

def test_task_for_deleted_paper_does_nothing(client):
    assert fetch_paper_metadata(88888) is None

def test_duplicate_save_does_not_fetch_again(authorized_client, test_papers, monkeypatch):
    calls = []
    monkeypatch.setattr(arxiv, "_request", lambda params: calls.append(params) or make_feed([make_entry()]))
    res = authorized_client.post("/papers/", json={"arxiv_id": "1810.04805"})   # already in the library
    assert res.status_code == 409
    assert calls == []


# ---------- retry ----------

def mark(session, paper_id, **values):
    session.query(models.Paper).filter(models.Paper.id == paper_id).update(values)
    session.commit()

def test_retry_failed_paper(authorized_client, test_papers, session):
    paper_id = test_papers[2].id
    mark(session, paper_id, status="failed", error="arXiv took too long to respond")

    res = authorized_client.post(f"/papers/{paper_id}/retry")
    assert res.status_code == 202
    assert res.json()["status"] == "pending"
    assert res.json()["error"] is None

    paper = get_paper(authorized_client, paper_id)
    assert paper.status == "done"
    assert paper.title == "Test paper 1912.09363"

def test_retry_pending_paper(authorized_client, test_papers):
    paper_id = test_papers[2].id        # saved but never fetched, e.g. the server restarted mid-task
    res = authorized_client.post(f"/papers/{paper_id}/retry")
    assert res.status_code == 202
    assert get_paper(authorized_client, paper_id).status == "done"

def test_retry_can_fail_again(authorized_client, test_papers, session, monkeypatch):
    paper_id = test_papers[2].id
    mark(session, paper_id, status="failed", error="old error")
    monkeypatch.setattr(arxiv, "_request", raising(arxiv.ArxivError("arXiv returned HTTP 503")))

    assert authorized_client.post(f"/papers/{paper_id}/retry").status_code == 202
    paper = get_paper(authorized_client, paper_id)
    assert paper.status == "failed"
    assert paper.error == "arXiv returned HTTP 503"

def test_retry_done_paper_is_refused(authorized_client, test_papers):
    res = authorized_client.post(f"/papers/{test_papers[0].id}/retry")
    assert res.status_code == 409

def test_retry_other_user_paper(authorized_client, test_papers, session):
    paper_id = test_papers[3].id
    mark(session, paper_id, status="failed", error="x")
    assert authorized_client.post(f"/papers/{paper_id}/retry").status_code == 404

def test_retry_paper_not_exist(authorized_client, test_papers):
    assert authorized_client.post("/papers/88888/retry").status_code == 404

def test_unauthorized_user_retry(client, test_papers):
    assert client.post(f"/papers/{test_papers[2].id}/retry").status_code == 401


# ---------- search ----------

def search_feed(params):
    return make_feed([
        make_entry("1706.03762", title="Attention Is All You Need"),
        make_entry("1810.04805", title="BERT"),
        make_entry("2005.14165", title="Language Models are Few-Shot Learners"),
    ])

def test_search_marks_papers_already_in_library(authorized_client, test_papers, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", search_feed)
    res = authorized_client.get("/arxiv/search", params={"q": "transformers"})
    results = [schemas.ArxivResult(**r) for r in res.json()]

    assert res.status_code == 200
    assert [r.arxiv_id for r in results] == ["1706.03762", "1810.04805", "2005.14165"]
    assert [r.in_library for r in results] == [True, True, False]
    assert results[0].title == "Attention Is All You Need"

def test_search_forwards_query_and_paging(authorized_client, monkeypatch):
    seen = {}
    monkeypatch.setattr(arxiv, "_request", lambda params: seen.update(params) or make_feed([]))
    res = authorized_client.get("/arxiv/search", params={"q": "temporal fusion", "limit": 5, "start": 10})

    assert res.status_code == 200 and res.json() == []
    assert seen["search_query"] == "all:temporal AND all:fusion"
    assert seen["max_results"] == 5 and seen["start"] == 10

@pytest.mark.parametrize("pasted", ["1706.03762", "arXiv:1706.03762v7", "https://arxiv.org/abs/1706.03762"])
def test_search_with_pasted_id_looks_up_that_paper(authorized_client, monkeypatch, pasted):
    seen = {}
    def fake(params):
        seen.update(params)
        return make_feed([make_entry("1706.03762")])
    monkeypatch.setattr(arxiv, "_request", fake)

    res = authorized_client.get("/arxiv/search", params={"q": pasted})
    assert res.status_code == 200
    assert seen == {"id_list": "1706.03762", "max_results": 1}
    assert [r["arxiv_id"] for r in res.json()] == ["1706.03762"]

def test_search_with_pasted_id_not_found(authorized_client, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", lambda params: make_feed([]))
    res = authorized_client.get("/arxiv/search", params={"q": "1706.99999"})
    assert res.status_code == 200
    assert res.json() == []

def test_search_when_arxiv_is_down(authorized_client, monkeypatch):
    monkeypatch.setattr(arxiv, "_request", raising(arxiv.ArxivError("could not reach arXiv")))
    res = authorized_client.get("/arxiv/search", params={"q": "transformers"})
    assert res.status_code == 502
    assert res.json()["detail"] == "could not reach arXiv"

@pytest.mark.parametrize("q", ["", "!!!", '"()"'])
def test_search_text_with_nothing_searchable(authorized_client, monkeypatch, q):
    calls = []
    monkeypatch.setattr(arxiv, "_request", lambda params: calls.append(params) or make_feed([]))
    res = authorized_client.get("/arxiv/search", params={"q": q})
    assert res.status_code == 422
    assert calls == []          # arXiv is not called for nothing

@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"start": -1}])
def test_search_paging_bounds(authorized_client, params):
    res = authorized_client.get("/arxiv/search", params={"q": "transformers", **params})
    assert res.status_code == 422

def test_unauthorized_user_search(client):
    assert client.get("/arxiv/search", params={"q": "transformers"}).status_code == 401

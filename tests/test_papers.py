import pytest
from app import models, schemas


# ---------- create ----------

def test_create_paper(authorized_client, test_user):
    res = authorized_client.post("/papers/", json={"arxiv_id": "2005.14165"})
    paper = schemas.Paper(**res.json())

    assert res.status_code == 201
    assert paper.arxiv_id == "2005.14165"
    assert paper.owner_id == test_user["id"]
    assert paper.status == "pending"
    assert paper.title is None

@pytest.mark.parametrize("value", [
    "https://arxiv.org/abs/2005.14165v2",
    "arXiv:2005.14165",
    "2005.14165v3",
])
def test_create_paper_normalizes_id(authorized_client, value):
    res = authorized_client.post("/papers/", json={"arxiv_id": value})
    assert res.status_code == 201
    assert res.json()["arxiv_id"] == "2005.14165"

@pytest.mark.parametrize("value", ["hello", "", "https://example.com/abs/1706.03762"])
def test_create_paper_invalid_id(authorized_client, value):
    res = authorized_client.post("/papers/", json={"arxiv_id": value})
    assert res.status_code == 422

def test_create_paper_missing_id(authorized_client):
    res = authorized_client.post("/papers/", json={})
    assert res.status_code == 422

def test_create_duplicate_paper(authorized_client, test_papers):
    res = authorized_client.post("/papers/", json={"arxiv_id": "1810.04805"})
    assert res.status_code == 409

def test_duplicate_detected_across_id_formats(authorized_client, test_papers):
    res = authorized_client.post("/papers/", json={"arxiv_id": "https://arxiv.org/abs/1810.04805v2"})
    assert res.status_code == 409

def test_two_users_can_save_same_paper(test_papers):
    ids = [(p.owner_id, p.arxiv_id) for p in test_papers if p.arxiv_id == "1706.03762"]
    assert len(ids) == 2 and ids[0][0] != ids[1][0]

def test_unauthorized_user_create_paper(client):
    res = client.post("/papers/", json={"arxiv_id": "2005.14165"})
    assert res.status_code == 401


# ---------- list ----------

def test_get_all_papers_only_own(authorized_client, test_user, test_papers):
    res = authorized_client.get("/papers/")
    papers = [schemas.Paper(**p) for p in res.json()]

    assert res.status_code == 200
    assert len(papers) == 3
    assert all(p.owner_id == test_user["id"] for p in papers)

def test_get_all_papers_newest_first(authorized_client, test_papers):
    res = authorized_client.get("/papers/")
    ids = [p["id"] for p in res.json()]
    assert ids == sorted(ids, reverse=True)

def test_papers_pagination(authorized_client, test_papers):
    first = authorized_client.get("/papers/?limit=2")
    rest = authorized_client.get("/papers/?limit=2&skip=2")

    assert len(first.json()) == 2
    assert len(rest.json()) == 1
    assert not {p["id"] for p in first.json()} & {p["id"] for p in rest.json()}

@pytest.mark.parametrize("query", ["limit=0", "limit=101", "skip=-1"])
def test_papers_pagination_bounds(authorized_client, test_papers, query):
    res = authorized_client.get(f"/papers/?{query}")
    assert res.status_code == 422

@pytest.mark.parametrize("search, expected_count", [
    ("attention", 1),       # title, case-insensitive
    ("BERT", 1),
    ("vaswani", 1),         # authors
    ("1912", 1),            # arxiv id
    ("transformers", 1),
    ("nothing-matches", 0),
    ("%", 0),               # wildcard characters are taken literally
    ("_", 0),
])
def test_search_papers(authorized_client, test_papers, search, expected_count):
    res = authorized_client.get("/papers/", params={"search": search})
    assert res.status_code == 200
    assert len(res.json()) == expected_count

@pytest.mark.parametrize("paper_status, expected_count", [("done", 2), ("pending", 1), ("failed", 0)])
def test_filter_papers_by_status(authorized_client, test_papers, paper_status, expected_count):
    res = authorized_client.get("/papers/", params={"status": paper_status})
    assert res.status_code == 200
    assert len(res.json()) == expected_count
    assert all(p["status"] == paper_status for p in res.json())

def test_filter_papers_invalid_status(authorized_client, test_papers):
    res = authorized_client.get("/papers/", params={"status": "bogus"})
    assert res.status_code == 422

def test_unauthorized_user_get_all_papers(client, test_papers):
    res = client.get("/papers/")
    assert res.status_code == 401


# ---------- get one ----------

def test_get_one_paper(authorized_client, test_papers):
    res = authorized_client.get(f"/papers/{test_papers[0].id}")
    paper = schemas.Paper(**res.json())

    assert res.status_code == 200
    assert paper.id == test_papers[0].id
    assert paper.title == test_papers[0].title
    assert paper.arxiv_id == "1706.03762"

def test_get_one_paper_not_exist(authorized_client, test_papers):
    res = authorized_client.get("/papers/88888")
    assert res.status_code == 404

def test_get_other_user_paper(authorized_client, test_papers):
    res = authorized_client.get(f"/papers/{test_papers[3].id}")
    assert res.status_code == 404

def test_unauthorized_user_get_one_paper(client, test_papers):
    res = client.get(f"/papers/{test_papers[0].id}")
    assert res.status_code == 401


# ---------- delete ----------

def test_delete_paper_success(authorized_client, test_papers):
    res = authorized_client.delete(f"/papers/{test_papers[0].id}")
    assert res.status_code == 204

    assert authorized_client.get(f"/papers/{test_papers[0].id}").status_code == 404
    assert len(authorized_client.get("/papers/").json()) == 2

def test_delete_paper_not_exist(authorized_client, test_papers):
    res = authorized_client.delete("/papers/88888")
    assert res.status_code == 404

def test_delete_other_user_paper(authorized_client, test_papers, session):
    res = authorized_client.delete(f"/papers/{test_papers[3].id}")
    assert res.status_code == 404
    assert session.query(models.Paper).filter(models.Paper.id == test_papers[3].id).first() is not None

def test_unauthorized_user_delete_paper(client, test_papers):
    res = client.delete(f"/papers/{test_papers[0].id}")
    assert res.status_code == 401

def test_deleting_user_deletes_their_papers(test_user, test_papers, session):
    session.query(models.User).filter(models.User.id == test_user["id"]).delete()
    session.commit()

    remaining = session.query(models.Paper).all()
    assert len(remaining) == 1
    assert remaining[0].owner_id != test_user["id"]

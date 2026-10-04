from datetime import datetime, timezone

import pytest

from app import models
from app.services import bibtex


def make_paper(arxiv_id="1706.03762", title="Attention Is All You Need", authors="Ashish Vaswani, Noam Shazeer", year=2017):
    return models.Paper(arxiv_id=arxiv_id, title=title, authors=authors,
                        published_at=datetime(year, 6, 12, tzinfo=timezone.utc) if year else None)


# ---------- formatting ----------

def test_entry_layout():
    assert bibtex.paper_to_bibtex(make_paper()) == (
        "@misc{vaswani2017attention,\n"
        "  author        = {Ashish Vaswani and Noam Shazeer},\n"
        "  title         = {{Attention Is All You Need}},\n"
        "  year          = {2017},\n"
        "  eprint        = {1706.03762},\n"
        "  archivePrefix = {arXiv},\n"
        "  url           = {https://arxiv.org/abs/1706.03762},\n"
        "}\n"
    )

def test_entry_without_authors_or_date_leaves_those_fields_out():
    entry = bibtex.paper_to_bibtex(make_paper(authors=None, year=None))
    assert "author" not in entry and "year" not in entry
    assert entry.startswith("@misc{arxiv_1706_03762,")

@pytest.mark.parametrize("kwargs, key", [
    ({}, "vaswani2017attention"),
    ({"authors": "Jacob Devlin", "title": "BERT: Pre-training of Deep Bidirectional Transformers", "year": 2018}, "devlin2018bert"),
    ({"authors": "Łukasz Kaiser, X Y"}, "kaiser2017attention"),                  # accents are dropped
    ({"authors": "José Álvarez"}, "alvarez2017attention"),
    ({"title": "The Illusion of Thinking"}, "vaswani2017illusion"),               # skips filler words
    ({"year": None}, "vaswaniattention"),
    ({"authors": None}, "arxiv_1706_03762"),
    ({"authors": None, "arxiv_id": "hep-th/9901001"}, "arxiv_hep_th_9901001"),    # old-style ids contain a slash
    ({"title": "!!!"}, "arxiv_1706_03762"),
    ({"title": "R&D at 100% of the $\\alpha$-divergence"}, "vaswani2017alpha"),   # skips one-letter and numeric words
    ({"title": "GPT-4 Technical Report"}, "vaswani2017gpt"),
    ({"title": "Go to 42"}, "vaswani2017go"),                                       # nothing better: falls back to the first word
])
def test_cite_key(kwargs, key):
    assert bibtex.cite_key(make_paper(**kwargs)) == key

@pytest.mark.parametrize("title, expected", [
    ("R&D at 100% #1", r"R\&D at 100\% \#1"),
    (r"Already \& escaped", r"Already \& escaped"),
    (r"The $\alpha$-divergence", r"The $\alpha$-divergence"),                     # LaTeX from arXiv is left alone
    ("Line\n   wrapped   title", "Line wrapped title"),
    ("Unbalanced { brace", "Unbalanced  brace"),
    ("Backwards } then {", "Backwards  then "),
    ("Fine {Bold} braces", "Fine {Bold} braces"),
])
def test_title_is_made_safe_for_bibtex(title, expected):
    entry = bibtex.paper_to_bibtex(make_paper(title=title))
    assert "title         = {{" + expected + "}}," in entry

def test_same_key_twice_gets_letters():
    papers = [make_paper("1706.03762"), make_paper("1706.00001"), make_paper("1706.00002")]
    keys = [line.split("{")[1].rstrip(",") for line in bibtex.papers_to_bibtex(papers).splitlines() if line.startswith("@misc")]
    assert keys == ["vaswani2017attention", "vaswani2017attentiona", "vaswani2017attentionb"]

def test_no_papers_gives_empty_text():
    assert bibtex.papers_to_bibtex([]) == ""


# ---------- one paper ----------

def test_get_paper_bibtex(authorized_client, test_papers):
    res = authorized_client.get(f"/papers/{test_papers[0].id}/bibtex")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert res.text.startswith("@misc{vaswani2017attention,")
    assert "eprint        = {1706.03762}" in res.text

def test_get_bibtex_of_paper_not_fetched_yet(authorized_client, test_papers):
    res = authorized_client.get(f"/papers/{test_papers[2].id}/bibtex")      # still pending
    assert res.status_code == 409

def test_get_bibtex_of_other_user_paper(authorized_client, test_papers):
    assert authorized_client.get(f"/papers/{test_papers[3].id}/bibtex").status_code == 404

def test_get_bibtex_paper_not_exist(authorized_client, test_papers):
    assert authorized_client.get("/papers/88888/bibtex").status_code == 404

def test_unauthorized_get_bibtex(client, test_papers):
    assert client.get(f"/papers/{test_papers[0].id}/bibtex").status_code == 401


# ---------- whole library ----------

def test_export_library(authorized_client, test_papers):
    res = authorized_client.get("/export/bibtex")
    assert res.status_code == 200
    assert res.text.count("@misc{") == 2                       # the two finished papers; user two's is not included
    assert "vaswani2017attention" in res.text and "devlin2018bert" in res.text
    assert res.headers["x-skipped-papers"] == "1"              # the pending one
    assert 'filename="library.bib"' in res.headers["content-disposition"]

def test_export_selected_papers(authorized_client, test_papers):
    res = authorized_client.get("/export/bibtex", params={"ids": [test_papers[1].id]})
    assert res.text.count("@misc{") == 1 and "devlin2018bert" in res.text
    assert res.headers["x-skipped-papers"] == "0"

def test_export_selected_counts_unfinished_papers_as_skipped(authorized_client, test_papers):
    res = authorized_client.get("/export/bibtex", params={"ids": [test_papers[0].id, test_papers[2].id]})
    assert res.text.count("@misc{") == 1
    assert res.headers["x-skipped-papers"] == "1"

def test_export_ignores_ids_of_other_users(authorized_client, test_papers):
    res = authorized_client.get("/export/bibtex", params={"ids": [test_papers[3].id]})
    assert res.status_code == 200 and res.text == ""
    assert res.headers["x-skipped-papers"] == "0"

def test_export_empty_library(authorized_client):
    res = authorized_client.get("/export/bibtex")
    assert res.status_code == 200 and res.text == ""

def test_unauthorized_export(client, test_papers):
    assert client.get("/export/bibtex").status_code == 401

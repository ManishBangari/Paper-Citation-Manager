import pytest
from app import models, schemas


# ---------- create ----------

def test_create_note(authorized_client, test_user, test_papers):
    paper_id = test_papers[2].id   # read fixture values before the request: the app closes the shared test session
    res = authorized_client.post(f"/papers/{paper_id}/notes", json={"content": "read this on the train"})
    note = schemas.Note(**res.json())

    assert res.status_code == 201
    assert note.content == "read this on the train"
    assert note.paper_id == paper_id
    assert note.owner_id == test_user["id"]

def test_create_note_trims_whitespace(authorized_client, test_papers):
    res = authorized_client.post(f"/papers/{test_papers[0].id}/notes", json={"content": "   padded   \n"})
    assert res.status_code == 201
    assert res.json()["content"] == "padded"

@pytest.mark.parametrize("payload", [
    {"content": ""},
    {"content": "   \n\t "},
    {},
    {"content": "x" * 10001},
])
def test_create_note_invalid(authorized_client, test_papers, payload):
    res = authorized_client.post(f"/papers/{test_papers[0].id}/notes", json=payload)
    assert res.status_code == 422

def test_create_note_max_length_ok(authorized_client, test_papers):
    res = authorized_client.post(f"/papers/{test_papers[0].id}/notes", json={"content": "x" * 10000})
    assert res.status_code == 201

def test_create_note_on_paper_not_exist(authorized_client, test_papers):
    res = authorized_client.post("/papers/88888/notes", json={"content": "hello"})
    assert res.status_code == 404

def test_create_note_on_other_user_paper(authorized_client, test_papers):
    res = authorized_client.post(f"/papers/{test_papers[3].id}/notes", json={"content": "sneaky"})
    assert res.status_code == 404

def test_unauthorized_user_create_note(client, test_papers):
    res = client.post(f"/papers/{test_papers[0].id}/notes", json={"content": "hello"})
    assert res.status_code == 401


# ---------- list notes of one paper ----------

def test_get_paper_notes(authorized_client, test_papers, test_notes):
    res = authorized_client.get(f"/papers/{test_papers[0].id}/notes")
    notes = [schemas.Note(**n) for n in res.json()]

    assert res.status_code == 200
    assert len(notes) == 2
    assert all(n.paper_id == test_papers[0].id for n in notes)

def test_get_paper_notes_newest_first(authorized_client, test_papers, test_notes):
    res = authorized_client.get(f"/papers/{test_papers[0].id}/notes")
    ids = [n["id"] for n in res.json()]
    assert ids == sorted(ids, reverse=True)

def test_get_paper_notes_empty(authorized_client, test_papers, test_notes):
    res = authorized_client.get(f"/papers/{test_papers[2].id}/notes")
    assert res.status_code == 200
    assert res.json() == []

def test_get_paper_notes_pagination(authorized_client, test_papers, test_notes):
    first = authorized_client.get(f"/papers/{test_papers[0].id}/notes?limit=1")
    second = authorized_client.get(f"/papers/{test_papers[0].id}/notes?limit=1&skip=1")

    assert len(first.json()) == 1 and len(second.json()) == 1
    assert first.json()[0]["id"] != second.json()[0]["id"]

@pytest.mark.parametrize("query", ["limit=0", "limit=201", "skip=-1"])
def test_get_paper_notes_pagination_bounds(authorized_client, test_papers, query):
    res = authorized_client.get(f"/papers/{test_papers[0].id}/notes?{query}")
    assert res.status_code == 422

def test_get_notes_of_other_user_paper(authorized_client, test_papers, test_notes):
    res = authorized_client.get(f"/papers/{test_papers[3].id}/notes")
    assert res.status_code == 404

def test_get_notes_of_paper_not_exist(authorized_client, test_papers):
    res = authorized_client.get("/papers/88888/notes")
    assert res.status_code == 404

def test_unauthorized_user_get_paper_notes(client, test_papers, test_notes):
    res = client.get(f"/papers/{test_papers[0].id}/notes")
    assert res.status_code == 401


# ---------- search across all notes ----------

def test_search_notes_returns_only_own(authorized_client, test_user, test_notes):
    res = authorized_client.get("/notes/")
    assert res.status_code == 200
    assert len(res.json()) == 3
    assert all(n["owner_id"] == test_user["id"] for n in res.json())

@pytest.mark.parametrize("search, expected_count", [
    ("attention", 1),        # case-insensitive, and user two's note about attention is not included
    ("ATTENTION", 1),
    ("softmax", 1),
    ("bert", 1),
    ("nothing-matches", 0),
    ("%", 1),                # taken literally: only the note that really contains "%" (not all 3)
    ("_", 1),                # same for "_" (only the note containing "d_k")
])
def test_search_notes(authorized_client, test_notes, search, expected_count):
    res = authorized_client.get("/notes/", params={"search": search})
    assert res.status_code == 200
    assert len(res.json()) == expected_count

def test_search_notes_filter_by_paper(authorized_client, test_papers, test_notes):
    res = authorized_client.get("/notes/", params={"paper_id": test_papers[0].id})
    assert len(res.json()) == 2
    assert all(n["paper_id"] == test_papers[0].id for n in res.json())

def test_unauthorized_user_search_notes(client, test_notes):
    res = client.get("/notes/")
    assert res.status_code == 401


# ---------- update ----------

def test_update_note(authorized_client, test_notes):
    note_id, paper_id = test_notes[0].id, test_notes[0].paper_id
    res = authorized_client.put(f"/notes/{note_id}", json={"content": "rewritten note"})
    note = schemas.Note(**res.json())

    assert res.status_code == 200
    assert note.content == "rewritten note"
    assert note.id == note_id
    assert note.paper_id == paper_id
    assert note.updated_at > note.created_at

@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "  "}, {}])
def test_update_note_invalid(authorized_client, test_notes, payload):
    res = authorized_client.put(f"/notes/{test_notes[0].id}", json=payload)
    assert res.status_code == 422

def test_update_other_user_note(authorized_client, test_notes, session):
    note_id = test_notes[3].id
    res = authorized_client.put(f"/notes/{note_id}", json={"content": "hijacked"})
    assert res.status_code == 404

    unchanged = session.query(models.Note).filter(models.Note.id == note_id).first()
    assert unchanged.content == "user two private note about attention"

def test_update_note_not_exist(authorized_client, test_notes):
    res = authorized_client.put("/notes/88888", json={"content": "hello"})
    assert res.status_code == 404

def test_unauthorized_user_update_note(client, test_notes):
    res = client.put(f"/notes/{test_notes[0].id}", json={"content": "hello"})
    assert res.status_code == 401


# ---------- delete ----------

def test_delete_note(authorized_client, test_papers, test_notes):
    paper_id, deleted_id, kept_id = test_papers[0].id, test_notes[0].id, test_notes[1].id
    res = authorized_client.delete(f"/notes/{deleted_id}")
    assert res.status_code == 204

    remaining = authorized_client.get(f"/papers/{paper_id}/notes").json()
    assert [n["id"] for n in remaining] == [kept_id]

def test_delete_note_not_exist(authorized_client, test_notes):
    res = authorized_client.delete("/notes/88888")
    assert res.status_code == 404

def test_delete_other_user_note(authorized_client, test_notes, session):
    note_id = test_notes[3].id
    res = authorized_client.delete(f"/notes/{note_id}")
    assert res.status_code == 404
    assert session.query(models.Note).filter(models.Note.id == note_id).first() is not None

def test_unauthorized_user_delete_note(client, test_notes):
    res = client.delete(f"/notes/{test_notes[0].id}")
    assert res.status_code == 401


# ---------- cascades ----------

def test_deleting_paper_deletes_its_notes(authorized_client, test_papers, test_notes, session):
    paper_id = test_papers[0].id
    res = authorized_client.delete(f"/papers/{paper_id}")
    assert res.status_code == 204

    left = session.query(models.Note).filter(models.Note.paper_id == paper_id).count()
    assert left == 0
    # notes of other papers are untouched
    assert session.query(models.Note).count() == 2

def test_deleting_user_deletes_their_notes(test_user, test_notes, session):
    session.query(models.User).filter(models.User.id == test_user["id"]).delete()
    session.commit()

    remaining = session.query(models.Note).all()
    assert len(remaining) == 1
    assert remaining[0].owner_id != test_user["id"]

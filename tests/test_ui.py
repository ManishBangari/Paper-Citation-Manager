"""Drives the Streamlit UI with Streamlit's own test runner, against the real API (test database, fake arXiv, fake Redis)."""
from pathlib import Path

import httpx
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from app import models
from app.services import arxiv

UI_FILE = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")


@pytest.fixture
def start_ui(client, test_user, token):
    """start_ui() opens the UI logged in as test_user; start_ui(logged_in=False) opens it as a visitor."""
    def start(logged_in=True, **state):
        at = AppTest.from_file(UI_FILE, default_timeout=30)
        at.session_state["_http_client"] = client
        if logged_in:
            at.session_state["token"] = token
            at.session_state["email"] = test_user["email"]
        for key, value in state.items():
            at.session_state[key] = value
        return at.run()
    return start


@pytest.fixture
def api(client, token):
    """Asks the API directly, to check what the UI really did."""
    return lambda method, path, **kw: client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kw)


def page_text(at):
    parts = []
    for group in (at.markdown, at.caption, at.header, at.subheader, at.success, at.info, at.warning, at.error):
        parts += [str(e.value) for e in group]
    return "\n".join(parts)


def button_keys(at):
    return [b.key for b in at.button]


def search_for(at, text):
    at.text_input(key="search_text").input(text)
    return at.button(key="search_submit").click().run()


# ---------- visitors: log in and sign up ----------

def test_visitor_sees_the_login_page(start_ui):
    at = start_ui(logged_in=False)
    assert not at.exception
    assert at.title[0].value == "Paper & Citation Manager"
    assert len(at.tabs) == 2

def test_sign_up_creates_the_account_and_logs_in(start_ui, client):
    at = start_ui(logged_in=False)
    at.text_input(key="signup_email").input("new@example.com")
    at.text_input(key="signup_password").input("secret123")
    at.button(key="signup_submit").click().run()

    assert not at.exception and at.session_state["token"]
    assert "new@example.com" in " ".join(m.value for m in at.sidebar.markdown)
    assert client.post("/login", data={"username": "new@example.com", "password": "secret123"}).status_code == 200

def test_sign_up_with_a_taken_email(start_ui, test_user):
    at = start_ui(logged_in=False)
    at.text_input(key="signup_email").input(test_user["email"])
    at.text_input(key="signup_password").input("whatever")
    at.button(key="signup_submit").click().run()
    assert "already registered" in at.error[0].value
    assert not at.session_state["token"]

def test_sign_up_with_an_invalid_email(start_ui):
    at = start_ui(logged_in=False)
    at.text_input(key="signup_email").input("not-an-email")
    at.text_input(key="signup_password").input("whatever")
    at.button(key="signup_submit").click().run()
    assert at.error and not at.exception
    assert not at.session_state["token"]

def test_log_in(start_ui, test_user):
    at = start_ui(logged_in=False)
    at.text_input(key="login_email").input(test_user["email"])
    at.text_input(key="login_password").input(test_user["password"])
    at.button(key="login_submit").click().run()
    assert at.session_state["token"] and not at.exception
    assert at.header[0].value == "Search arXiv"

def test_log_in_with_a_wrong_password(start_ui, test_user):
    at = start_ui(logged_in=False)
    at.text_input(key="login_email").input(test_user["email"])
    at.text_input(key="login_password").input("wrong")
    at.button(key="login_submit").click().run()
    assert at.error[0].value == "Wrong email or password."
    assert not at.session_state["token"]

def test_log_in_with_an_empty_form(start_ui):
    at = start_ui(logged_in=False)
    at.button(key="login_submit").click().run()
    assert at.warning and not at.session_state["token"]

def test_log_out(start_ui):
    at = start_ui()
    at.button(key="logout").click().run()
    assert not at.session_state["token"]
    assert at.title[0].value == "Paper & Citation Manager"

def test_an_expired_session_sends_you_back_to_the_login_page(start_ui):
    at = start_ui(token="not-a-valid-token", page="My library")
    assert at.title[0].value == "Paper & Citation Manager"
    assert "session expired" in at.info[0].value

def test_the_ui_says_so_when_the_api_is_down(start_ui):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    at = start_ui(logged_in=False, _http_client=httpx.Client(base_url="http://api", transport=httpx.MockTransport(refuse)))
    at.text_input(key="login_email").input("a@b.com")
    at.text_input(key="login_password").input("x")
    at.button(key="login_submit").click().run()
    assert "Cannot reach the API" in at.error[0].value and not at.exception


# ---------- search ----------

def test_search_shows_results_and_saving_adds_to_the_library(start_ui, api):
    at = search_for(start_ui(), "transformers")
    text = page_text(at)
    assert "Attention Is All You Need" in text and "BERT" in text
    assert "save_1706.03762" in button_keys(at)

    at.button(key="save_1706.03762").click().run()
    assert "Saved to your library." in page_text(at)
    assert "✓ In your library" in page_text(at)
    assert "save_1706.03762" not in button_keys(at)

    library = api("GET", "/papers/").json()
    assert [(p["arxiv_id"], p["status"], p["title"]) for p in library] == [("1706.03762", "done", "Attention Is All You Need")]

def test_search_marks_papers_already_in_the_library(start_ui, test_papers):
    at = search_for(start_ui(), "transformers")
    assert page_text(at).count("✓ In your library") == 2
    assert not [k for k in button_keys(at) if k.startswith("save_")]

def test_search_with_nothing_typed(start_ui):
    at = start_ui()
    at.button(key="search_submit").click().run()
    assert at.warning

def test_search_failure_is_shown_not_raised(start_ui, monkeypatch):
    def down(params):
        raise arxiv.ArxivError("could not reach arXiv")
    monkeypatch.setattr(arxiv, "_request", down)
    at = search_for(start_ui(), "transformers")
    assert "Search failed: could not reach arXiv" in at.error[0].value
    assert not at.exception

def test_search_with_a_pasted_arxiv_url(start_ui):
    at = search_for(start_ui(), "https://arxiv.org/abs/2005.14165v2")
    assert "Test paper 2005.14165" in page_text(at)


# ---------- library ----------

def test_library_lists_own_papers_with_their_status(start_ui, test_papers):
    at = start_ui(page="My library")
    text = page_text(at)
    assert "✅ **Attention Is All You Need**" in text
    assert "⏳ **arXiv:1912.09363**" in text                   # pending: no title yet
    assert len([k for k in button_keys(at) if k.startswith("open_")]) == 3     # user two's paper is not shown
    assert f"retry_{test_papers[2].id}" in button_keys(at)
    assert f"retry_{test_papers[0].id}" not in button_keys(at)

def test_empty_library_says_so(start_ui):
    assert "library is empty" in page_text(start_ui(page="My library"))

@pytest.mark.parametrize("widget, value, expected", [
    ("selectbox:lib_status", "done", 2),
    ("selectbox:lib_status", "pending", 1),
    ("text_input:lib_filter", "bert", 1),
    ("text_input:lib_filter", "nothing-matches", 0),
])
def test_library_filters(start_ui, test_papers, widget, value, expected):
    at = start_ui(page="My library")
    kind, key = widget.split(":")
    (at.selectbox(key=key).select(value) if kind == "selectbox" else at.text_input(key=key).input(value)).run()
    assert len([k for k in button_keys(at) if k.startswith("open_")]) == expected

def test_retry_a_failed_paper(start_ui, test_papers, session, api):
    paper_id = test_papers[2].id
    session.query(models.Paper).filter(models.Paper.id == paper_id).update({"status": "failed", "error": "could not reach arXiv"})
    session.commit()

    at = start_ui(page="My library")
    assert "Could not fetch the details: could not reach arXiv" in page_text(at)
    at.button(key=f"retry_{paper_id}").click().run()
    assert "Fetching the paper's details again" in page_text(at)
    assert api("GET", f"/papers/{paper_id}").json()["status"] == "done"

def test_delete_asks_for_confirmation_first(start_ui, test_papers, api):
    paper_id = test_papers[0].id
    at = start_ui(page="My library")

    at.button(key=f"delete_{paper_id}").click().run()
    assert "Delete this paper and all its notes?" in at.warning[0].value
    assert api("GET", f"/papers/{paper_id}").status_code == 200          # nothing deleted yet

    at.button(key=f"no_{paper_id}").click().run()                       # cancel
    assert not at.warning and api("GET", f"/papers/{paper_id}").status_code == 200

    at.button(key=f"delete_{paper_id}").click().run()
    at.button(key=f"yes_{paper_id}").click().run()
    assert "Paper deleted." in page_text(at)
    assert api("GET", f"/papers/{paper_id}").status_code == 404

def test_export_bibtex(start_ui, test_papers):
    at = start_ui(page="My library")
    at.button(key="export_all").click().run()
    code = at.code[0].value
    assert code.count("@misc{") == 2 and "vaswani2017attention" in code
    assert "1 paper(s) were skipped" in page_text(at)

def test_export_with_nothing_to_export(start_ui):
    at = start_ui(page="My library")
    at.button(key="export_all").click().run()
    assert "Nothing to export yet" in page_text(at)


# ---------- one paper ----------

def test_open_a_paper_shows_details_and_bibtex(start_ui, test_papers):
    paper_id = test_papers[0].id
    at = start_ui(page="My library")
    at.button(key=f"open_{paper_id}").click().run()

    assert at.header[0].value == "Attention Is All You Need"
    assert "@misc{vaswani2017attention," in at.code[0].value
    assert "Ashish Vaswani" in page_text(at)

    at.button(key="back").click().run()
    assert at.header[0].value == "My library"

def test_a_pending_paper_has_no_bibtex_but_can_be_retried(start_ui, test_papers, api):
    paper_id = test_papers[2].id
    at = start_ui(paper_id=paper_id)
    assert not at.code
    at.button(key="retry_detail").click().run()
    assert api("GET", f"/papers/{paper_id}").json()["status"] == "done"

def test_notes_can_be_added_edited_and_deleted(start_ui, test_papers, api):
    paper_id = test_papers[0].id
    at = start_ui(paper_id=paper_id)
    assert "No notes yet." in page_text(at)

    at.text_area(key="new_note").input("Scaled dot-product: divide by $\\sqrt{d_k}$")
    at.button(key="add_note").click().run()
    assert "Note added." in page_text(at)
    notes = api("GET", f"/papers/{paper_id}/notes").json()
    assert [n["content"] for n in notes] == ["Scaled dot-product: divide by $\\sqrt{d_k}$"]
    note_id = notes[0]["id"]

    at.button(key=f"edit_{note_id}").click().run()
    at.text_area(key=f"edit_text_{note_id}").input("rewritten")
    at.button(key=f"edit_save_{note_id}").click().run()
    assert "Note saved." in page_text(at) and "edited" in page_text(at)
    assert api("GET", f"/papers/{paper_id}/notes").json()[0]["content"] == "rewritten"

    at.button(key=f"delete_note_{note_id}").click().run()
    assert "Note deleted." in page_text(at)
    assert api("GET", f"/papers/{paper_id}/notes").json() == []

def test_cancelling_an_edit_keeps_the_note(start_ui, test_papers, test_notes, api):
    note = test_notes[0]
    at = start_ui(paper_id=test_papers[0].id)
    at.button(key=f"edit_{note.id}").click().run()
    at.text_area(key=f"edit_text_{note.id}").input("changed my mind")
    at.button(key=f"edit_cancel_{note.id}").click().run()
    assert api("GET", f"/papers/{test_papers[0].id}/notes").json()[1]["content"] == note.content

def test_an_empty_note_is_refused(start_ui, test_papers, api):
    at = start_ui(paper_id=test_papers[0].id)
    at.text_area(key="new_note").input("   ")
    at.button(key="add_note").click().run()
    assert "cannot be empty" in at.warning[0].value
    assert api("GET", f"/papers/{test_papers[0].id}/notes").json() == []

def test_search_notes_and_jump_to_the_paper(start_ui, test_papers, test_notes):
    at = start_ui(page="My library")
    at.text_input(key="notes_query").input("softmax")
    at.button(key="notes_search_submit").click().run()
    assert "In: Attention Is All You Need" in page_text(at)

    at.button(key=f"hit_{test_notes[0].id}").click().run()
    assert at.header[0].value == "Attention Is All You Need"

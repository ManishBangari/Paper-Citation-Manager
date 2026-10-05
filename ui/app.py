"""Paper & Citation Manager: a small Streamlit front end.

It only talks to the API at API_URL and has no database code.
Run it with:  API_URL=http://localhost:8000 streamlit run ui/app.py
"""
import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
PAGE_SIZE = 10
STATUS_ICON = {"done": "✅", "pending": "⏳", "failed": "❌"}

st.set_page_config(page_title="Paper & Citation Manager", page_icon="📚")


# ---------- talking to the API ----------

@st.cache_resource
def default_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=30, follow_redirects=True)


def http() -> httpx.Client:
    # the tests put their own client in session_state["_http_client"]
    return st.session_state.get("_http_client") or default_client()


def message(res: httpx.Response) -> str:
    try:
        detail = res.json()["detail"]
    except (ValueError, KeyError, TypeError):
        return f"unexpected answer from the API (HTTP {res.status_code})"
    if isinstance(detail, list):        # validation errors
        return "; ".join(str(d.get("msg", d)) for d in detail)
    return str(detail)


def call(method: str, path: str, auth: bool = True, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {st.session_state.token}"} if auth else {}
    try:
        res = http().request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError:
        st.error(f"Cannot reach the API at {API_URL}. Is it running?")
        st.stop()
    if auth and res.status_code == 401:
        log_out("Your session expired, please log in again.")
        st.rerun()
    return res


# ---------- state ----------

def init_state():
    defaults = {"token": None, "email": None, "notice": None, "flash": None, "page": "Search arXiv", "paper_id": None,
                "query": "", "start": 0, "results": None, "search_error": None,
                "lib_skip": 0, "confirm_delete": None, "bibtex_all": None, "note_hits": None, "editing_note": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def log_out(notice: str = None):
    for key in ["token", "email", "paper_id", "query", "start", "results", "search_error", "lib_skip",
                "confirm_delete", "bibtex_all", "note_hits", "editing_note", "flash"]:
        st.session_state.pop(key, None)
    st.session_state.notice = notice


def show_flash():
    if st.session_state.flash:
        st.success(st.session_state.flash)
        st.session_state.flash = None


def flash_and_rerun(text: str):
    st.session_state.flash = text
    st.rerun()


def close_paper():
    st.session_state.paper_id = None


def date_of(iso: str) -> str:
    return (iso or "")[:10]


# ---------- log in / sign up ----------

def log_in(email: str, password: str):
    res = call("POST", "/login", auth=False, data={"username": email, "password": password})
    if res.status_code != 200:
        st.error("Wrong email or password." if res.status_code == 403 else message(res))
        return
    st.session_state.token = res.json()["access_token"]
    st.session_state.email = email
    st.rerun()


def login_page():
    st.title("Paper & Citation Manager")
    st.caption("Search arXiv, keep a library of papers, take notes and export BibTeX.")
    if st.session_state.notice:
        st.info(st.session_state.notice)
        st.session_state.notice = None

    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", key="login_submit")
        if submitted:
            if email.strip() and password:
                log_in(email.strip(), password)
            else:
                st.warning("Enter your email and password.")

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            submitted = st.form_submit_button("Create account", key="signup_submit")
        if submitted:
            if not (email.strip() and password):
                st.warning("Enter an email and a password.")
            else:
                res = call("POST", "/users/", auth=False, json={"email": email.strip(), "password": password})
                if res.status_code == 201:
                    log_in(email.strip(), password)
                elif res.status_code == 409:
                    st.error("That email is already registered. Try logging in.")
                else:
                    st.error(message(res))


def sidebar():
    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.email}**")
        st.radio("Go to", ["Search arXiv", "My library"], key="page", on_change=close_paper)
        if st.button("Log out", key="logout"):
            log_out()
            st.rerun()


# ---------- search ----------

def run_search():
    res = call("GET", "/arxiv/search", params={"q": st.session_state.query, "limit": PAGE_SIZE,
                                               "start": st.session_state.start})
    if res.status_code == 200:
        st.session_state.results, st.session_state.search_error = res.json(), None
    else:
        st.session_state.results, st.session_state.search_error = None, message(res)


def save_paper(result: dict):
    res = call("POST", "/papers/", json={"arxiv_id": result["arxiv_id"]})
    if res.status_code in (201, 409):
        st.session_state.results = [{**r, "in_library": True} if r["arxiv_id"] == result["arxiv_id"] else r
                                    for r in st.session_state.results]
        flash_and_rerun("Saved to your library." if res.status_code == 201 else "That paper is already in your library.")
    else:
        st.error(message(res))


def result_card(r: dict):
    with st.container(border=True):
        st.markdown(f"**{r['title']}**")
        st.caption(f"{r['authors']} · {date_of(r['published_at'])} · arXiv:{r['arxiv_id']}")
        with st.expander("Abstract"):
            st.write(r["abstract"])
        left, right = st.columns(2)
        left.markdown(f"[PDF]({r['pdf_url']})")
        if r["in_library"]:
            right.caption("✓ In your library")
        elif right.button("Save to library", key=f"save_{r['arxiv_id']}"):
            save_paper(r)


def search_page():
    st.header("Search arXiv")
    show_flash()
    with st.form("search_form"):
        text = st.text_input("Keywords, or paste an arXiv ID or URL", key="search_text")
        submitted = st.form_submit_button("Search", key="search_submit")
    if submitted:
        if text.strip():
            st.session_state.query, st.session_state.start = text.strip(), 0
            run_search()
        else:
            st.warning("Type something to search for.")

    if st.session_state.search_error:
        st.error(f"Search failed: {st.session_state.search_error}")
    results = st.session_state.results
    if results is None:
        return
    if not results:
        st.info("No papers found.")
    for r in results:
        result_card(r)

    start = st.session_state.start
    prev_col, next_col = st.columns(2)
    if prev_col.button("◀ Previous", key="search_prev", disabled=start == 0):
        st.session_state.start = max(start - PAGE_SIZE, 0)
        run_search()
        st.rerun()
    if next_col.button("Next ▶", key="search_next", disabled=len(results) < PAGE_SIZE):
        st.session_state.start = start + PAGE_SIZE
        run_search()
        st.rerun()


# ---------- library ----------

def reset_library_page():
    st.session_state.lib_skip = 0


def retry_paper(paper_id: int):
    res = call("POST", f"/papers/{paper_id}/retry")
    if res.status_code == 202:
        flash_and_rerun("Fetching the paper's details again. Press Refresh in a few seconds.")
    st.error(message(res))


def delete_paper(paper_id: int):
    res = call("DELETE", f"/papers/{paper_id}")
    if res.status_code == 204:
        st.session_state.confirm_delete = None
        flash_and_rerun("Paper deleted.")
    st.error(message(res))


def paper_row(p: dict):
    with st.container(border=True):
        st.markdown(f"{STATUS_ICON[p['status']]} **{p['title'] or 'arXiv:' + p['arxiv_id']}**")
        st.caption(" · ".join(x for x in [p["authors"], date_of(p["published_at"]), f"arXiv:{p['arxiv_id']}"] if x))
        if p["status"] == "failed":
            st.caption(f"Could not fetch the details: {p['error']}")
        elif p["status"] == "pending":
            st.caption("Fetching the details from arXiv. Press Refresh in a few seconds.")

        open_col, retry_col, delete_col = st.columns(3)
        if open_col.button("Open", key=f"open_{p['id']}"):
            st.session_state.paper_id = p["id"]
            st.rerun()
        if p["status"] != "done" and retry_col.button("Retry", key=f"retry_{p['id']}"):
            retry_paper(p["id"])
        if delete_col.button("Delete", key=f"delete_{p['id']}"):
            st.session_state.confirm_delete = p["id"]
            st.rerun()

        if st.session_state.confirm_delete == p["id"]:
            st.warning("Delete this paper and all its notes?")
            yes_col, no_col = st.columns(2)
            if yes_col.button("Yes, delete", key=f"yes_{p['id']}"):
                delete_paper(p["id"])
            if no_col.button("Cancel", key=f"no_{p['id']}"):
                st.session_state.confirm_delete = None
                st.rerun()


def export_section():
    st.divider()
    if st.button("Export library as BibTeX", key="export_all"):
        res = call("GET", "/export/bibtex")
        if res.status_code == 200:
            st.session_state.bibtex_all = (res.text, int(res.headers.get("x-skipped-papers", 0)))
        else:
            st.error(message(res))
    if st.session_state.bibtex_all:
        text, skipped = st.session_state.bibtex_all
        if text:
            st.download_button("Download library.bib", text, file_name="library.bib", mime="text/plain", key="download_bib")
            st.code(text, language="bibtex")
        else:
            st.info("Nothing to export yet: no paper has its details fetched.")
        if skipped:
            st.caption(f"{skipped} paper(s) were skipped because their details are not fetched yet.")


def notes_search_section():
    with st.expander("Search my notes"):
        with st.form("notes_search_form"):
            text = st.text_input("Text in a note", key="notes_query")
            submitted = st.form_submit_button("Search notes", key="notes_search_submit")
        if submitted and text.strip():
            res = call("GET", "/notes/", params={"search": text.strip(), "limit": 20})
            if res.status_code == 200:
                hits = res.json()
                titles = {}
                for pid in {n["paper_id"] for n in hits}:
                    paper = call("GET", f"/papers/{pid}")
                    titles[pid] = (paper.json().get("title") or f"arXiv:{paper.json()['arxiv_id']}") if paper.status_code == 200 else f"paper {pid}"
                st.session_state.note_hits = [{**n, "paper_title": titles[n["paper_id"]]} for n in hits]
            else:
                st.error(message(res))
        hits = st.session_state.note_hits
        if hits is not None and not hits:
            st.info("No notes match.")
        for n in hits or []:
            with st.container(border=True):
                st.caption(f"In: {n['paper_title']}")
                st.markdown(n["content"])
                if st.button("Open paper", key=f"hit_{n['id']}"):
                    st.session_state.paper_id = n["paper_id"]
                    st.rerun()


def library_page():
    st.header("My library")
    show_flash()
    filter_col, status_col, refresh_col = st.columns([3, 2, 1])
    text = filter_col.text_input("Filter by title, author or arXiv ID", key="lib_filter", on_change=reset_library_page)
    status = status_col.selectbox("Status", ["all", "done", "pending", "failed"], key="lib_status", on_change=reset_library_page)
    refresh_col.write("")
    refresh_col.button("Refresh", key="lib_refresh")

    params = {"limit": PAGE_SIZE, "skip": st.session_state.lib_skip}
    if text.strip():
        params["search"] = text.strip()
    if status != "all":
        params["status"] = status
    res = call("GET", "/papers/", params=params)
    if res.status_code != 200:
        st.error(message(res))
        return
    papers = res.json()

    if not papers:
        st.info("No papers match." if text.strip() or status != "all" or st.session_state.lib_skip
                else "Your library is empty. Search arXiv and save some papers.")
    for p in papers:
        paper_row(p)

    skip = st.session_state.lib_skip
    prev_col, next_col = st.columns(2)
    if prev_col.button("◀ Previous", key="lib_prev", disabled=skip == 0):
        st.session_state.lib_skip = max(skip - PAGE_SIZE, 0)
        st.rerun()
    if next_col.button("Next ▶", key="lib_next", disabled=len(papers) < PAGE_SIZE):
        st.session_state.lib_skip = skip + PAGE_SIZE
        st.rerun()

    export_section()
    notes_search_section()


# ---------- one paper ----------

def note_card(n: dict):
    with st.container(border=True):
        if st.session_state.editing_note == n["id"]:
            new_text = st.text_area("Edit note", value=n["content"], key=f"edit_text_{n['id']}")
            save_col, cancel_col = st.columns(2)
            if save_col.button("Save", key=f"edit_save_{n['id']}"):
                res = call("PUT", f"/notes/{n['id']}", json={"content": new_text})
                if res.status_code == 200:
                    st.session_state.editing_note = None
                    flash_and_rerun("Note saved.")
                st.error(message(res))
            if cancel_col.button("Cancel", key=f"edit_cancel_{n['id']}"):
                st.session_state.editing_note = None
                st.rerun()
            return

        st.markdown(n["content"])
        edited = " · edited" if n["updated_at"] != n["created_at"] else ""
        st.caption(f"{n['created_at'][:16].replace('T', ' ')} UTC{edited}")
        edit_col, delete_col = st.columns(2)
        if edit_col.button("Edit", key=f"edit_{n['id']}"):
            st.session_state.editing_note = n["id"]
            st.rerun()
        if delete_col.button("Delete note", key=f"delete_note_{n['id']}"):
            res = call("DELETE", f"/notes/{n['id']}")
            if res.status_code == 204:
                flash_and_rerun("Note deleted.")
            st.error(message(res))


def notes_section(paper_id: int):
    st.subheader("Notes")
    with st.form("add_note_form", clear_on_submit=True):
        text = st.text_area("New note (Markdown and $LaTeX$ work)", key="new_note")
        added = st.form_submit_button("Add note", key="add_note")
    if added:
        if not text.strip():
            st.warning("A note cannot be empty.")
        else:
            res = call("POST", f"/papers/{paper_id}/notes", json={"content": text})
            if res.status_code == 201:
                flash_and_rerun("Note added.")
            st.error(message(res))

    res = call("GET", f"/papers/{paper_id}/notes", params={"limit": 200})
    notes = res.json() if res.status_code == 200 else []
    if not notes:
        st.caption("No notes yet.")
    for n in notes:
        note_card(n)


def paper_page():
    paper_id = st.session_state.paper_id
    if st.button("← Back to library", key="back"):
        st.session_state.paper_id = None
        st.rerun()
    show_flash()

    res = call("GET", f"/papers/{paper_id}")
    if res.status_code != 200:
        st.error(message(res))
        return
    p = res.json()

    st.header(p["title"] or f"arXiv:{p['arxiv_id']}")
    st.caption(" · ".join(x for x in [p["authors"], date_of(p["published_at"])] if x))
    st.markdown(f"{STATUS_ICON[p['status']]} **{p['status']}** · [arXiv page](https://arxiv.org/abs/{p['arxiv_id']})"
                + (f" · [PDF]({p['pdf_url']})" if p["pdf_url"] else ""))
    if p["status"] != "done":
        st.caption(f"Could not fetch the details: {p['error']}" if p["status"] == "failed"
                   else "Fetching the details from arXiv.")
        if st.button("Retry fetching details", key="retry_detail"):
            retry_paper(paper_id)
    if p["abstract"]:
        st.subheader("Abstract")
        st.write(p["abstract"])

    if p["status"] == "done":
        st.subheader("BibTeX")
        bib = call("GET", f"/papers/{paper_id}/bibtex")
        st.code(bib.text if bib.status_code == 200 else message(bib), language="bibtex")

    st.divider()
    notes_section(paper_id)


# ---------- page router ----------

def main():
    init_state()
    if not st.session_state.token:
        login_page()
        return

    sidebar()
    if st.session_state.paper_id is not None:
        paper_page()
    elif st.session_state.page == "Search arXiv":
        search_page()
    else:
        library_page()


main()

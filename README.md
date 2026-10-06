# Paper & Citation Manager

[![CI](https://github.com/ManishBangari/Paper-Citation-Manager/actions/workflows/build-deploy.yaml/badge.svg)](https://github.com/ManishBangari/Paper-Citation-Manager/actions/workflows/build-deploy.yaml)

A personal research library. Search arXiv, save papers, keep notes on them and export BibTeX, through a REST API
(FastAPI) and a small web interface (Streamlit).

## What you can do

- **Search arXiv** by keywords, or paste an arXiv ID or URL. Results show the abstract and tell you which papers are already in your library.
- **Save papers.** A saved paper appears immediately as `pending`; its title, authors, abstract and PDF link are fetched from arXiv in the background and the paper becomes `done`, or `failed` with the reason (and a Retry button).
- **Take notes** on any paper: add, edit and delete. Notes accept Markdown and `$LaTeX$`, and you can search across all of them.
- **Export BibTeX** for one paper or the whole library.
- Everything is private to your account.

## How it fits together

```
 Streamlit UI  ──HTTP──►  FastAPI  ──►  PostgreSQL   users, papers, notes (SQLAlchemy + Alembic migrations)
   (ui/app.py)             │
                           ├──►  Redis        cache of arXiv answers + the shared "one request per 3 seconds" limiter (optional)
                           │
                           └──►  arXiv API    called from background tasks and the search endpoint
```

| Part | Technology |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT login |
| Data | PostgreSQL, Redis |
| UI | Streamlit |
| Tests | pytest, fakeredis, Streamlit's `AppTest` |
| Delivery | Docker, Docker Compose, GitHub Actions |

## Quick start with Docker

You need Docker Engine with the `docker compose` plugin.

```bash
cp .env.example .env        # then set SECRET_KEY, for example:  openssl rand -hex 32
docker compose -f docker-compose-dev.yml up --build
```

- Web interface: http://localhost:8501
- API and interactive docs: http://localhost:8000/docs

The first start creates the database tables by itself (`alembic upgrade head`). In this setup compose supplies the
database and Redis settings, so only `SECRET_KEY` has to be in `.env`.

## Running without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # API, tests and UI

cp .env.example .env                         # database settings and SECRET_KEY; see "Configuration"
alembic upgrade head                         # needs a running PostgreSQL

uvicorn app.main:app --reload                # API on http://localhost:8000
streamlit run ui/app.py                      # UI on http://localhost:8501 (new terminal)
```

Redis is optional. Without it everything works; searches are just not cached and the 3-second limiter only covers a
single server process. To try it: `docker run -d -p 6379:6379 redis:7-alpine`.

## Tests

```bash
python -m pytest                 # everything
python -m pytest tests/test_ui.py              # one file
python -m pytest -k bibtex                     # by name
```

The tests need a PostgreSQL (they use a separate database called `<DATABASE_NAME>_test`) but nothing else: Redis is
replaced by `fakeredis`, arXiv by canned responses, and the UI is driven headlessly with Streamlit's test runner.
Because they never touch the network, a separate opt-in check calls the real arXiv API:

```bash
ARXIV_LIVE=1 python -m pytest tests/test_arxiv_live.py
```

## API

Log in with `POST /login` (form fields `username` = email, `password`) and send the token as `Authorization: Bearer <token>`.
Interactive documentation is at `/docs`. Use the trailing slash exactly as shown (`/papers/`, `/notes/`); without it the API answers with a redirect.

| Method and path | What it does |
|---|---|
| `POST /users/` | Create an account |
| `POST /login` | Get a token |
| `GET /users/{id}` | Your own account details |
| `GET /arxiv/search?q=&limit=&start=` | Search arXiv, or look up a pasted ID or URL. Marks papers already in your library |
| `POST /papers/` | Save a paper by arXiv ID or URL (details are fetched in the background) |
| `GET /papers/` | Your library. Filters: `search`, `status` (`pending`, `done`, `failed`), `limit`, `skip` |
| `GET /papers/{id}` · `DELETE /papers/{id}` | One paper · delete it and its notes |
| `POST /papers/{id}/retry` | Fetch the details again after a failure |
| `GET /papers/{id}/bibtex` | BibTeX entry for one paper |
| `GET /export/bibtex?ids=` | BibTeX for the whole library, or only the listed papers |
| `POST /papers/{id}/notes` · `GET /papers/{id}/notes` | Add a note · list a paper's notes |
| `GET /notes/?search=&paper_id=` | Search across all your notes |
| `PUT /notes/{id}` · `DELETE /notes/{id}` | Edit · delete a note |

Another user's paper or note is reported as `404`, never `403`, so nobody can discover which ids exist.

## Design notes

**Saving a paper is asynchronous.** `POST /papers/` stores the row as `pending` and answers at once; a FastAPI background
task then asks arXiv for the details and marks the paper `done` or `failed` (with a readable error). A failed paper can be retried with
`POST /papers/{id}/retry`. The task opens its own database session, because the request's session is closed by then.

**Redis does two jobs, and is optional.**
- *Cache:* search results are kept for an hour and a paper's details for a day. Search results also fill the per-paper cache, so saving a paper you just found needs no extra arXiv call. Errors and empty results are never cached, and the cache holds nothing user-specific (the "already in your library" flag is added per request).
- *Rate limit:* arXiv asks for at most one request every 3 seconds. The next free slot is a Redis key with a 3-second expiry (`SET NX PX`, which is atomic), so the limit holds across all worker processes. Search gives up after 8 seconds of waiting (HTTP 502), background fetches wait up to 60.
- *If Redis is down,* the cache is skipped, the limiter falls back to one inside the process, and Redis is not retried for 30 seconds, so an outage costs one error instead of one per request.

**arXiv search.** Filler words ("is", "all", "you") are dropped from the query, because arXiv returns nothing when a term it does not index is required. If matching every word finds nothing, the search is repeated matching any word.

**BibTeX.** Entries are `@misc` with `eprint` and `archivePrefix`, and a readable key such as `vaswani2017attention` (duplicates get a letter). Characters that break BibTeX (`& % #`) are escaped and unbalanced braces removed; LaTeX that arXiv titles already contain is left alone.

## Configuration

| Variable | Used by | Meaning |
|---|---|---|
| `DATABASE_HOSTNAME`, `DATABASE_PORT`, `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_NAME` | API | PostgreSQL connection |
| `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` | API | JWT signing key, algorithm (`HS256`) and token lifetime |
| `REDIS_URL` | API | Defaults to `redis://localhost:6379/0`; the app works without a Redis server |
| `CORS_ORIGINS` | API | Comma-separated browser origins allowed to call the API. Empty by default, because the UI calls the API from its own server |
| `API_URL` | UI | Where the API is. Defaults to `http://localhost:8000` |

For the production compose file (`docker-compose-prod.yml`) use a separate `.env` on the server with
`DATABASE_HOSTNAME=postgres` and `DATABASE_PORT=5432`.

## Project layout

```
app/
  main.py, config.py, database.py, models.py, schemas.py, oauth2.py, utils.py
  cache.py                 Redis cache helpers (never required)
  routers/                 users, auth, papers, notes, arxiv, bibtex
  services/
    arxiv.py               arXiv client: parsing, search, caching
    ratelimit.py           one request per 3 seconds, shared through Redis
    papers.py              the background task that fetches a paper's details
    bibtex.py              BibTeX formatting
alembic/versions/          database migrations
ui/app.py                  the Streamlit interface (talks to the API only)
tests/                     pytest suite
```

## Known limits

- Background tasks run inside the API process. A restart can leave a paper `pending` (use Retry), and a burst of saves
  occupies worker threads while they wait for the arXiv limiter. A job queue (Celery, ARQ) would fix both; it was left out to keep the project small.
- Access tokens last `ACCESS_TOKEN_EXPIRE_MINUTES` and are not refreshed; the UI sends you back to the login page when one expires.
- Only arXiv metadata is stored, not the PDFs.
- `passlib` and `python-jose` are older libraries; `bcrypt` and `PyJWT` are the usual replacements.

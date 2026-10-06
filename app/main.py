from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import users, auth, papers, notes, arxiv, bibtex
from .config import settings

# the tables are created by Alembic migrations (alembic upgrade head), not by the app

app = FastAPI(title="Paper & Citation Manager")

# the Streamlit UI calls this API from its own server, so no browser origin is allowed unless CORS_ORIGINS lists it
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Paper & Citation Manager API"}


app.include_router(users.router)
app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(notes.router)
app.include_router(arxiv.router)
app.include_router(bibtex.router)

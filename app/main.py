from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routers import post, users, auth, vote, papers, notes, arxiv, bibtex
from .config import settings

# posts?limit=5&skip=0&search=welcome%50post
# models.Base.metadata.create_all(bind=engine)

app = FastAPI()

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# my_posts = [{"title": "title of post 1", "content": "content of post 1", "id": 1}, {"title": "favorite foods", "content": "I like pizza", "id": 2}]

# def find_post(id):
#     for p in my_posts:
#         if p["id"] == id:
#             return p
        
# request get method in "/" url
@app.get("/")
def root():
    return {"message": "welcome to the FastAPI"}

app.include_router(post.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(vote.router)
app.include_router(papers.router)
app.include_router(notes.router)
app.include_router(arxiv.router)
app.include_router(bibtex.router)

'''
@app.get("/sqlalchemy")
def test_posts(db: Session = Depends(get_db)): 
    posts = db.query(models.Post).all()
    print(posts)
    return {"data": "successful"}
'''






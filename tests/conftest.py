from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.main import app
from app.oauth2 import create_access_token
from app.config import settings
from app.database import get_db, Base
from app import models, database
from app.services import arxiv as arxiv_service
from tests import arxiv_samples
from alembic import command


# SQLALCHEMY_DATABASE_URL = 'postgresql://postgres:password123@localhost:5432/fastapi_test'
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg://{settings.database_username}:"
    f"{settings.database_password}@{settings.database_hostname}:"
    f"{settings.database_port}/{settings.database_name}_test"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# client = TestClient(app)

@pytest.fixture()
def session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try: 
        yield db
    finally:
        db.close()
    
@pytest.fixture()
def client(session, monkeypatch):
    def override_get_db():
        try:
            yield session
        finally:
            session.close()


    app.dependency_overrides[get_db] = override_get_db
    # background tasks open their own session and call arXiv: point them at the test database and a fake arXiv
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(arxiv_service, "_request", arxiv_samples.default_fake_request)
    yield TestClient(app)

@pytest.fixture
def test_user2(client):
    user_data = {"email":"example123@gmail.com",
                 "password":"password123"}
    res = client.post("/users/", json=user_data)

    assert res.status_code == 201
    # print(res.json())
    new_user = res.json()
    new_user['password'] = user_data['password']

    return new_user

@pytest.fixture
def test_user(client):
    user_data = {"email":"example@gmail.com",
                 "password":"password123"}
    res = client.post("/users/", json=user_data)

    assert res.status_code == 201
    # print(res.json())
    new_user = res.json()
    new_user['password'] = user_data['password']

    return new_user

@pytest.fixture
def token(test_user):
    return create_access_token({"user_id": test_user['id']})


@pytest.fixture
def authorized_client(client, token):
    client.headers = {
        **client.headers,
        "Authorization": f"Bearer {token}"
    }

    return client

@pytest.fixture
def test_posts(test_user, session, test_user2):
    posts_data = [{
        "title": "first title",
        "content": "first content",
        "owner_id": test_user['id']
    }, {
        "title": "2nd title",
        "content": "2nd content",
        "owner_id": test_user['id']
    },
        {
        "title": "3rd title",
        "content": "3rd content",
        "owner_id": test_user['id']
    },
    {
            "title": "3rd title",
            "content": "3rd content",
            "owner_id": test_user2['id']
        }]

    def create_post_model(post):
        return models.Post(**post)
    
    post_map = map(create_post_model, posts_data)
    posts = list(post_map)

    session.add_all(posts)

    # session.add_all([models.user(title="first title", content="first content", owner_id=test_user['id']),
    #                 models.user(title="2nd title", content="2nd content", owner_id=test_user['id']),
    #                 models.user(title="3rd title", content="3rd content", owner_id=test_user['id'])
                    # ])

    session.commit()

    posts = session.query(models.Post).all()
    return posts

@pytest.fixture
def test_papers(test_user, test_user2, session):
    papers_data = [
        {"arxiv_id": "1706.03762", "title": "Attention Is All You Need",
         "authors": "Ashish Vaswani, Noam Shazeer", "status": "done", "owner_id": test_user['id']},
        {"arxiv_id": "1810.04805", "title": "BERT: Pre-training of Deep Bidirectional Transformers",
         "authors": "Jacob Devlin, Ming-Wei Chang", "status": "done", "owner_id": test_user['id']},
        {"arxiv_id": "1912.09363", "owner_id": test_user['id']},
        # same paper as the first one, saved by a different user
        {"arxiv_id": "1706.03762", "title": "Attention Is All You Need",
         "authors": "Ashish Vaswani, Noam Shazeer", "status": "done", "owner_id": test_user2['id']},
    ]

    session.add_all([models.Paper(**paper) for paper in papers_data])
    session.commit()

    return session.query(models.Paper).order_by(models.Paper.id).all()

@pytest.fixture
def test_notes(test_papers, test_user, test_user2, session):
    # test_papers[0], [1], [2] belong to test_user; test_papers[3] belongs to test_user2
    notes_data = [
        {"paper_id": test_papers[0].id, "owner_id": test_user['id'],
         "content": "Scaled dot-product: divide by sqrt(d_k) to stabilize softmax"},
        {"paper_id": test_papers[0].id, "owner_id": test_user['id'],
         "content": "Multi-head attention runs h attention functions in parallel"},
        {"paper_id": test_papers[1].id, "owner_id": test_user['id'],
         "content": "BERT masks 15% of the input tokens"},
        {"paper_id": test_papers[3].id, "owner_id": test_user2['id'],
         "content": "user two private note about attention"},
    ]

    session.add_all([models.Note(**note) for note in notes_data])
    session.commit()

    return session.query(models.Note).order_by(models.Note.id).all()

from app import schemas, models

import pytest
from jose import jwt
from app.config import settings

# def test_root(client):
#     res = client.get("/")
#     print(res.json().get("message"))
#     assert res.json().get("message") == "welcome to the FastAPI"
#     assert res.status_code == 200

def test_create_user(client):
    res = client.post("/users/", json={"email": "hello123@gmail.com", "password": "password123"})
    # print(res.json())
    new_user = schemas.UserOut(**res.json())
    assert new_user.email == "hello123@gmail.com"
    assert res.status_code == 201

def test_login_user(test_user, client):
    res = client.post("/login", data={"username": test_user["email"], "password": test_user["password"]})
    # print(res.json())
    login_res = schemas.Token(**res.json())
    payload = jwt.decode(login_res.access_token, settings.secret_key, algorithms=[settings.algorithm])
    
    id = payload.get("user_id")
    assert id == test_user["id"]
    assert login_res.token_type == "bearer"
    assert res.status_code == 200

@pytest.mark.parametrize("email, password, status_code", [
    ('wrongemail@gmail.com', 'password123', 403),
    ('sanjeev@gmail.com', 'wrongpassword', 403),
    ('wrongemail@gmail.com', 'wrongpassword', 403),
    (None, 'password123', 422),
    ('sanjeev@gmail.com', None, 422)
])
def test_incorrect_login(test_user, client, email, password, status_code):
    res = client.post("/login", data= {"username": email, "password": password})

    assert res.status_code == status_code
    # assert res.json().get("detail") == "Invalid Credentials"

def test_create_user_duplicate_email(test_user, client):
    res = client.post("/users/", json={"email": test_user["email"], "password": "anotherpassword"})
    assert res.status_code == 409

def test_token_of_deleted_user_is_rejected(authorized_client, test_user, session):
    session.query(models.User).filter(models.User.id == test_user["id"]).delete()
    session.commit()

    res = authorized_client.get("/posts/")
    assert res.status_code == 401

# making a schema class for posts
from pydantic import BaseModel, EmailStr, conint, ConfigDict, field_validator, Field
from datetime import datetime
from typing import Optional

from . import utils

class PostBase(BaseModel):
    title: str
    content: str
    published: bool = True # default value if true

class PostCreate(PostBase):
    pass

class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class Post(PostBase):
    id: int
    created_at: datetime
    owner_id: int
    owner: UserOut

    model_config = ConfigDict(from_attributes=True)

class PostOut(BaseModel):
    Post: Post
    votes: int

    model_config = ConfigDict(from_attributes=True)

        
class UserCreate(BaseModel):
    email: EmailStr
    password: str



class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[int] = None

class Vote(BaseModel):
    post_id: int
    dir: conint(ge=0, le=1)


class PaperCreate(BaseModel):
    arxiv_id: str

    @field_validator("arxiv_id")
    @classmethod
    def clean_arxiv_id(cls, v: str) -> str:
        return utils.normalize_arxiv_id(v)

class Paper(BaseModel):
    id: int
    owner_id: int
    arxiv_id: str
    title: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    published_at: Optional[datetime] = None
    pdf_url: Optional[str] = None
    status: str
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoteCreate(BaseModel):
    content: str = Field(max_length=10000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("note cannot be empty")
        return v

class Note(BaseModel):
    id: int
    paper_id: int
    owner_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

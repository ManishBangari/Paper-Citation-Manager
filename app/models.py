from sqlalchemy.orm import relationship

from .database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Text, UniqueConstraint, text, func
from sqlalchemy.sql.sqltypes import TIMESTAMP


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default='now()')
    phone_number = Column(String, nullable=True) # optional phone number field


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("owner_id", "arxiv_id", name="papers_owner_arxiv_uq"),)
    id = Column(Integer, primary_key=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    arxiv_id = Column(String, nullable=False)
    # metadata below is filled in later by the arXiv fetch, so it is nullable
    title = Column(String, nullable=True)
    authors = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    pdf_url = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default='pending')  # pending | done | failed
    error = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))

    owner = relationship("User")


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, nullable=False)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'), onupdate=func.now())

from typing import Literal, Optional

from .. import models, schemas, oauth2
from fastapi import Response, status, HTTPException, Depends, APIRouter, Query, BackgroundTasks
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.papers import fetch_paper_metadata


router = APIRouter(
    prefix="/papers",
    tags=['Papers']
)


def get_own_paper(id: int, db: Session, current_user: models.User):
    # a paper that belongs to someone else is reported as 404, so ids of other users' papers don't leak
    paper = db.query(models.Paper).filter(models.Paper.id == id, models.Paper.owner_id == current_user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"paper with id: {id} was not found")
    return paper


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Paper)
def create_paper(paper: schemas.PaperCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    new_paper = models.Paper(arxiv_id=paper.arxiv_id, owner_id=current_user.id)
    db.add(new_paper)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"paper {paper.arxiv_id} is already in your library")
    db.refresh(new_paper)

    # the response goes out as 'pending'; the metadata is filled in right after it is sent
    background_tasks.add_task(fetch_paper_metadata, new_paper.id)

    return new_paper


@router.get("/", response_model=list[schemas.Paper])
def get_papers(db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user),
               limit: int = Query(10, ge=1, le=100), skip: int = Query(0, ge=0), search: Optional[str] = "",
               paper_status: Optional[Literal["pending", "done", "failed"]] = Query(None, alias="status")):
    query = db.query(models.Paper).filter(models.Paper.owner_id == current_user.id)

    if search:
        query = query.filter(or_(
            models.Paper.title.icontains(search, autoescape=True),
            models.Paper.authors.icontains(search, autoescape=True),
            models.Paper.arxiv_id.icontains(search, autoescape=True),
        ))
    if paper_status:
        query = query.filter(models.Paper.status == paper_status)

    return query.order_by(models.Paper.created_at.desc(), models.Paper.id.desc()).limit(limit).offset(skip).all()


@router.get("/{id}", response_model=schemas.Paper)
def get_paper(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    return get_own_paper(id, db, current_user)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    paper = get_own_paper(id, db, current_user)
    db.delete(paper)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=schemas.Paper)
def retry_paper(id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    paper = get_own_paper(id, db, current_user)
    # 'pending' is allowed too: background tasks live in memory, so a server restart can leave a paper stuck there
    if paper.status == "done":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="this paper was already fetched from arXiv")

    paper.status = "pending"
    paper.error = None
    db.commit()
    db.refresh(paper)
    background_tasks.add_task(fetch_paper_metadata, paper.id)

    return paper

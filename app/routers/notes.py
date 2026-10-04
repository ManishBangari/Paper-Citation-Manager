from typing import Optional

from .. import models, schemas, oauth2
from .papers import get_own_paper
from fastapi import Response, status, HTTPException, Depends, APIRouter, Query
from sqlalchemy.orm import Session

from ..database import get_db


router = APIRouter(
    tags=['Notes']
)


def get_own_note(id: int, db: Session, current_user: models.User):
    # a note that belongs to someone else is reported as 404, same as papers
    note = db.query(models.Note).filter(models.Note.id == id, models.Note.owner_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"note with id: {id} was not found")
    return note


@router.post("/papers/{paper_id}/notes", status_code=status.HTTP_201_CREATED, response_model=schemas.Note)
def create_note(paper_id: int, note: schemas.NoteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    get_own_paper(paper_id, db, current_user)

    new_note = models.Note(paper_id=paper_id, owner_id=current_user.id, content=note.content)
    db.add(new_note)
    db.commit()
    db.refresh(new_note)

    return new_note


@router.get("/papers/{paper_id}/notes", response_model=list[schemas.Note])
def get_paper_notes(paper_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user),
                    limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)):
    get_own_paper(paper_id, db, current_user)

    return db.query(models.Note).filter(models.Note.paper_id == paper_id, models.Note.owner_id == current_user.id)\
        .order_by(models.Note.created_at.desc(), models.Note.id.desc()).limit(limit).offset(skip).all()


@router.get("/notes/", response_model=list[schemas.Note])
def search_notes(db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user),
                 search: Optional[str] = "", paper_id: Optional[int] = None,
                 limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)):
    query = db.query(models.Note).filter(models.Note.owner_id == current_user.id)

    if search:
        query = query.filter(models.Note.content.icontains(search, autoescape=True))
    if paper_id is not None:
        query = query.filter(models.Note.paper_id == paper_id)

    return query.order_by(models.Note.created_at.desc(), models.Note.id.desc()).limit(limit).offset(skip).all()


@router.put("/notes/{id}", response_model=schemas.Note)
def update_note(id: int, updated_note: schemas.NoteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    note = get_own_note(id, db, current_user)
    note.content = updated_note.content
    db.commit()
    db.refresh(note)

    return note


@router.delete("/notes/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    note = get_own_note(id, db, current_user)
    db.delete(note)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

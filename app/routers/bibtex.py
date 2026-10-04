from typing import Optional

from .. import models, oauth2
from .papers import get_own_paper
from ..services import bibtex
from fastapi import status, HTTPException, Depends, APIRouter, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..database import get_db


router = APIRouter(
    tags=['BibTeX']
)


def is_ready(paper: models.Paper) -> bool:
    return paper.status == "done" and bool(paper.title)


@router.get("/papers/{id}/bibtex", response_class=PlainTextResponse)
def get_paper_bibtex(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    paper = get_own_paper(id, db, current_user)
    if not is_ready(paper):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="this paper's details have not been fetched from arXiv yet")

    return PlainTextResponse(bibtex.paper_to_bibtex(paper))


@router.get("/export/bibtex", response_class=PlainTextResponse)
def export_bibtex(ids: Optional[list[int]] = Query(None), db: Session = Depends(get_db),
                  current_user: models.User = Depends(oauth2.get_current_user)):
    """Your whole library, or only the papers in ?ids=1&ids=2. Papers still pending or failed are skipped and counted."""
    query = db.query(models.Paper).filter(models.Paper.owner_id == current_user.id)
    if ids:
        query = query.filter(models.Paper.id.in_(ids))
    papers = query.order_by(models.Paper.id).all()

    ready = [p for p in papers if is_ready(p)]
    return PlainTextResponse(bibtex.papers_to_bibtex(ready), headers={
        "X-Skipped-Papers": str(len(papers) - len(ready)),
        "Content-Disposition": 'attachment; filename="library.bib"',
    })

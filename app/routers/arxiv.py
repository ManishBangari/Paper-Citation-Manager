from .. import models, schemas, oauth2, utils
from ..services import arxiv
from fastapi import status, HTTPException, Depends, APIRouter, Query
from sqlalchemy.orm import Session

from ..database import get_db


router = APIRouter(
    prefix="/arxiv",
    tags=['arXiv']
)


@router.get("/search", response_model=list[schemas.ArxivResult])
def search_arxiv(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(10, ge=1, le=50), start: int = Query(0, ge=0),
                 db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    # an arXiv id or URL pasted into the search box looks that one paper up instead of searching
    arxiv_id = None
    try:
        arxiv_id = utils.normalize_arxiv_id(q)
    except ValueError:
        try:
            arxiv.build_search_query(q)  # reject text with nothing searchable before calling arXiv
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    try:
        if arxiv_id:
            results = [arxiv.fetch_paper(arxiv_id)]
        else:
            results = arxiv.search_papers(q, limit=limit, start=start)
    except arxiv.ArxivNotFound:
        results = []
    except arxiv.ArxivError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    saved = {arxiv_id for (arxiv_id,) in db.query(models.Paper.arxiv_id).filter(
        models.Paper.owner_id == current_user.id,
        models.Paper.arxiv_id.in_([r["arxiv_id"] for r in results])).all()}

    return [{**r, "in_library": r["arxiv_id"] in saved} for r in results]

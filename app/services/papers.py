import logging

from .. import database, models
from . import arxiv

logger = logging.getLogger(__name__)


def fetch_paper_metadata(paper_id: int) -> None:
    """Background task: fill in a saved paper's metadata from arXiv.

    It opens its own database session, because the request's session is already closed by the
    time a background task runs. The paper always ends up 'done' or 'failed', never stuck on 'pending'.
    """
    db = database.SessionLocal()
    try:
        paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
        if paper is None:  # the user deleted it before the task got to run
            return

        try:
            data = arxiv.fetch_paper(paper.arxiv_id, max_wait=arxiv.BACKGROUND_MAX_WAIT)
        except arxiv.ArxivError as e:
            paper.status = "failed"
            paper.error = str(e)[:500]
        except Exception:
            logger.exception("unexpected error while fetching paper %s", paper_id)
            paper.status = "failed"
            paper.error = "unexpected error while fetching this paper"
        else:
            paper.title = data["title"]
            paper.authors = data["authors"]
            paper.abstract = data["abstract"]
            paper.published_at = data["published_at"]
            paper.pdf_url = data["pdf_url"]
            paper.status = "done"
            paper.error = None
        db.commit()
    finally:
        db.close()

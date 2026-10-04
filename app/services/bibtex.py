"""Turns saved papers into BibTeX entries (@misc with arXiv's eprint fields, which BibTeX and BibLaTeX both accept)."""
import re
import string
import unicodedata

from .. import models
from .arxiv import STOPWORDS


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += (ch == "{") - (ch == "}")
        if depth < 0:
            return False
    return depth == 0


def _clean(text) -> str:
    """arXiv titles are already written for LaTeX, so only the characters that would break BibTeX are touched."""
    text = " ".join((text or "").split())
    text = re.sub(r"(?<!\\)([&%#])", r"\\\1", text)       # & % # -> \& \% \#   (already escaped ones are kept)
    return text if _balanced(text) else text.replace("{", "").replace("}", "")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _author_list(paper: models.Paper) -> list[str]:
    return [a.strip() for a in (paper.authors or "").split(",") if a.strip()]


def cite_key(paper: models.Paper) -> str:
    """vaswani2017attention: first author's surname + year + first meaningful word of the title."""
    authors = _author_list(paper)
    words = re.findall(r"[A-Za-z0-9]+", _ascii(paper.title or ""))
    if authors and words:
        surname = re.sub(r"[^a-z0-9]", "", _ascii(authors[0].split()[-1]).lower())
        meaningful = [w for w in words if w.lower() not in STOPWORDS]
        word = next((w for w in meaningful if w.isalpha() and len(w) >= 3), (meaningful or words)[0]).lower()
        year = str(paper.published_at.year) if paper.published_at else ""
        if surname:
            return f"{surname}{year}{word}"
    return "arxiv_" + re.sub(r"[^A-Za-z0-9]+", "_", paper.arxiv_id).strip("_")


def paper_to_bibtex(paper: models.Paper, key: str = None) -> str:
    fields = []
    if paper.authors:
        fields.append(("author", " and ".join(_clean(a) for a in _author_list(paper))))
    fields.append(("title", "{" + _clean(paper.title) + "}"))       # double braces keep the capitals as written
    if paper.published_at:
        fields.append(("year", str(paper.published_at.year)))
    fields += [("eprint", paper.arxiv_id), ("archivePrefix", "arXiv"), ("url", f"https://arxiv.org/abs/{paper.arxiv_id}")]

    body = "".join(f"  {name:<13} = {{{value}}},\n" for name, value in fields)
    return f"@misc{{{key or cite_key(paper)},\n{body}}}\n"


def papers_to_bibtex(papers: list[models.Paper]) -> str:
    seen, entries = set(), []
    for paper in papers:
        key = cite_key(paper)
        if key in seen:     # two papers with the same surname, year and word: vaswani2017attention, ...a, ...b
            key = next((key + s for s in string.ascii_lowercase if key + s not in seen), f"{key}{len(seen)}")
        seen.add(key)
        entries.append(paper_to_bibtex(paper, key))
    return "\n".join(entries)

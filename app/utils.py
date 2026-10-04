import re

from passlib.context import CryptContext

pwd_context=CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

def hash(password: str):
    return pwd_context.hash(password)

def verify(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


# accepts "1706.03762", "1706.03762v7", "arXiv:1706.03762", abs/pdf URLs and old-style ids (hep-th/9901001)
_NEW_ID = r"\d{4}\.\d{4,5}"
_OLD_ID = r"[a-z\-]+(?:\.[A-Za-z]{2})?/\d{7}"
_ARXIV_RE = re.compile(
    rf"^(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:)?({_NEW_ID}|{_OLD_ID})(?:v\d+)?(?:\.pdf)?/?$",
    re.IGNORECASE,
)

def normalize_arxiv_id(value: str) -> str:
    match = _ARXIV_RE.match(value.strip())
    if not match:
        raise ValueError("not a valid arXiv id or URL")
    return match.group(1)

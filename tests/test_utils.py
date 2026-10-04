import pytest
from app.utils import normalize_arxiv_id


@pytest.mark.parametrize("value, expected", [
    ("1706.03762", "1706.03762"),
    ("1706.03762v7", "1706.03762"),
    ("  1706.03762  ", "1706.03762"),
    ("arXiv:1706.03762", "1706.03762"),
    ("https://arxiv.org/abs/1706.03762", "1706.03762"),
    ("https://arxiv.org/abs/1706.03762v5", "1706.03762"),
    ("http://www.arxiv.org/pdf/1706.03762.pdf", "1706.03762"),
    ("https://arxiv.org/pdf/1706.03762v7.pdf", "1706.03762"),
    ("2005.14165", "2005.14165"),
    ("hep-th/9901001", "hep-th/9901001"),
    ("math.GT/0309136v2", "math.GT/0309136"),
])
def test_normalize_arxiv_id(value, expected):
    assert normalize_arxiv_id(value) == expected


@pytest.mark.parametrize("value", [
    "",
    "hello",
    "1706.037",
    "170.03762",
    "https://example.com/abs/1706.03762",
    "https://arxiv.org/abs/",
    "1706.03762 and 1810.04805",
])
def test_normalize_arxiv_id_invalid(value):
    with pytest.raises(ValueError):
        normalize_arxiv_id(value)

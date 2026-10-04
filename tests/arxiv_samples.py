"""Hand-written arXiv Atom responses, so the tests never touch the network.

The abstracts are made-up filler text; only the structure matches what arXiv sends back.
"""

FEED_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">\n'
    '  <title type="html">ArXiv Query</title>\n'
    '  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">{total}</opensearch:totalResults>\n'
)


def make_entry(arxiv_id="1706.03762", version="v7", title="Attention Is All\n  You Need",
               authors=("Ashish Vaswani", "Noam Shazeer"), summary="Made-up abstract text\n  that wraps over two lines.",
               published="2017-06-12T17:57:34Z", pdf=True):
    author_xml = "".join(f"<author><name>{a}</name></author>" for a in authors)
    published_xml = f"<published>{published}</published>" if published else ""
    pdf_xml = f'<link title="pdf" href="http://arxiv.org/pdf/{arxiv_id}{version}" rel="related" type="application/pdf"/>' if pdf else ""
    return (
        "<entry>"
        f"<id>http://arxiv.org/abs/{arxiv_id}{version}</id>"
        f"<title>{title}</title>"
        f"<summary>{summary}</summary>"
        f"{published_xml}{author_xml}"
        f'<link href="http://arxiv.org/abs/{arxiv_id}{version}" rel="alternate" type="text/html"/>'
        f"{pdf_xml}"
        "</entry>\n"
    )


def make_feed(entries=()):
    entries = list(entries)
    return FEED_HEADER.format(total=len(entries)) + "".join(entries) + "</feed>"


def make_error_feed(message="incorrect id format for abc"):
    return make_feed([
        "<entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_abc</id>"
        f"<title>Error</title><summary>{message}</summary></entry>"
    ])


def default_fake_request(params):
    """Stands in for app.services.arxiv._request in every API test."""
    if "id_list" in params:
        paper_id = params["id_list"]
        return make_feed([make_entry(arxiv_id=paper_id, title=f"Test paper {paper_id}")])
    return make_feed([
        make_entry("1706.03762", title="Attention Is All You Need"),
        make_entry("1810.04805", title="BERT: Pre-training of Deep Bidirectional Transformers", authors=("Jacob Devlin",)),
    ])

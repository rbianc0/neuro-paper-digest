from neuro_digest.dedupe import deduplicate
from neuro_digest.models import AuthorRef, BlueskySignal, Candidate, SourceRecord


def test_same_doi_merges_sources_and_signal():
    a = Candidate(title="A paper", doi="10.1000/ABC", sources=[SourceRecord("openalex", "W1")]); b = Candidate(title="A paper", doi="https://doi.org/10.1000/abc", sources=[SourceRecord("crossref", "10.1000/abc")], bluesky_signals=[BlueskySignal(followed_actor="x.bsky.social")]); out = deduplicate([a, b]); assert len(out) == 1; assert set(out[0].source_types) == {"openalex", "crossref"}; assert len(out[0].bluesky_signals) == 1


def test_preprint_publication_mapping_collapses():
    pre = Candidate(title="Neural dynamics under fear", doi="10.1101/2026.01.01.123", preprint_doi="10.1101/2026.01.01.123", sources=[SourceRecord("biorxiv", "10.1101/2026.01.01.123")]); pub = Candidate(title="Neural dynamics under fear", doi="10.1038/xyz", preprint_doi="10.1101/2026.01.01.123", published_doi="10.1038/xyz", journal="Nature Neuroscience", sources=[SourceRecord("biorxiv_published_mapping", "10.1101/2026.01.01.123->10.1038/xyz")]); out = deduplicate([pre, pub]); assert len(out) == 1; assert out[0].doi == "10.1038/xyz"; assert out[0].preprint_doi == "10.1101/2026.01.01.123"


def test_structured_author_ids_survive_merge():
    a = Candidate(title="Structured author test", doi="10.1000/test", authors=[AuthorRef(name="Ada Lovelace", openalex_id="A1", position=0)]); b = Candidate(title="Structured author test", doi="10.1000/test", authors=[AuthorRef(name="Ada Lovelace", orcid="0000-0000-0000-000X", position=0)]); out = deduplicate([a, b])[0]; assert len(out.authors) == 1; assert out.authors[0].orcid == "0000-0000-0000-000X"; assert out.authors[0].openalex_id == "A1"

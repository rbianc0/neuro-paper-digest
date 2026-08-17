from neuro_digest.dedupe import deduplicate
from neuro_digest.models import Candidate, BlueskySignal

def test_same_doi_merges_sources_and_signal():
    a=Candidate(title="A paper",doi="10.1000/ABC",source_types=["openalex"]); b=Candidate(title="A paper",doi="https://doi.org/10.1000/abc",source_types=["bluesky"],bluesky_signals=[BlueskySignal(followed_actor="x.bsky.social")]); out=deduplicate([a,b]); assert len(out)==1; assert set(out[0].source_types)=={"openalex","bluesky"}; assert len(out[0].bluesky_signals)==1

def test_preprint_publication_mapping_collapses():
    pre=Candidate(title="Neural dynamics under fear",doi="10.1101/2026.01.01.123",preprint_doi="10.1101/2026.01.01.123",source_types=["biorxiv"]); pub=Candidate(title="Neural dynamics under fear",doi="10.1038/xyz",preprint_doi="10.1101/2026.01.01.123",published_doi="10.1038/xyz",journal="Nature Neuroscience",source_types=["biorxiv_published_mapping"]); out=deduplicate([pre,pub]); assert len(out)==1; assert out[0].doi=="10.1038/xyz"; assert out[0].preprint_doi=="10.1101/2026.01.01.123"

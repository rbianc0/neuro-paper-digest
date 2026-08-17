from neuro_digest.util import canonical_doi, normalized_title, extract_dois

def test_canonical_doi():
    assert canonical_doi("https://doi.org/10.1038/S41593-026-1234-5") == "10.1038/s41593-026-1234-5"
    assert canonical_doi("doi: 10.1101/2026.08.01.123456.") == "10.1101/2026.08.01.123456"

def test_extract_dois(): assert "10.1038/s41593-026-1234-5" in extract_dois("See https://doi.org/10.1038/s41593-026-1234-5")
def test_normalized_title(): assert normalized_title("Fear-Generalization: an fMRI study") == "fear generalization an fmri study"

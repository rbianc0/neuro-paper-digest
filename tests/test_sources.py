from neuro_digest.sources.crossref import candidate_from_message
from neuro_digest.sources.europe_pmc import candidate_from_result
from neuro_digest.sources.openalex import OpenAlexClient, candidate_from_work


def test_openalex_keeps_author_identity_and_abstract():
    work = {"id": "https://openalex.org/W123", "doi": "https://doi.org/10.1000/ABC", "display_name": "A paper", "publication_date": "2026-08-10", "type": "article", "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0000-0000-000X"}, "institutions": []}], "primary_location": {"landing_page_url": "https://example.org/paper", "source": {"display_name": "Neuron"}}, "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/12345/"}, "abstract_inverted_index": {"hello": [0], "world": [1]}}
    c = candidate_from_work(work, query="fear"); assert c.openalex_id == "W123"; assert c.authors[0].openalex_id == "A1"; assert c.authors[0].orcid == "0000-0000-0000-000X"; assert c.abstract == "hello world"; assert c.sources[0].external_id == "W123"


def test_crossref_parser():
    c = candidate_from_message({"DOI": "10.1000/ABC", "title": ["A Crossref paper"], "container-title": ["Neuron"], "published-online": {"date-parts": [[2026, 8, 12]]}, "author": [{"given": "Ada", "family": "Lovelace", "ORCID": "https://orcid.org/0000-0000-0000-000X"}], "abstract": "<jats:p>Useful abstract.</jats:p>"}); assert c.doi == "10.1000/abc"; assert c.publication_date == "2026-08-12"; assert c.authors[0].orcid == "0000-0000-0000-000X"; assert c.abstract == "Useful abstract."


def test_europe_pmc_parser():
    c = candidate_from_result({"source": "MED", "id": "12345", "pmid": "12345", "doi": "10.1000/ABC", "title": "Europe PMC paper", "journalTitle": "Neuron", "firstPublicationDate": "2026-08-11", "authorList": {"author": [{"fullName": "Ada Lovelace", "authorIdType": "ORCID", "authorId": "0000-0000-0000-000X"}]}, "abstractText": "An abstract", "citedByCount": 4}); assert c.pmid == "12345"; assert c.authors[0].orcid == "0000-0000-0000-000X"; assert c.cited_by_count == 4


def test_europe_pmc_non_med_id_is_not_mislabeled_as_pmid():
    c = candidate_from_result({"source": "PMC", "id": "PMC123", "title": "PMC paper"}); assert c.pmid is None


def test_openalex_global_field_ingestion_uses_cursor_and_neuro_psych_fields(monkeypatch):
    import neuro_digest.sources.openalex as module
    calls = []; responses = [{"results": [{"id": "https://openalex.org/W1", "display_name": "One", "publication_date": "2026-08-18", "authorships": [], "primary_location": {}, "ids": {}}], "meta": {"next_cursor": "next"}}, {"results": [{"id": "https://openalex.org/W2", "display_name": "Two", "publication_date": "2026-08-17", "authorships": [], "primary_location": {}, "ids": {}}], "meta": {"next_cursor": None}}]
    def fake_get_json(session, url, *, params=None, timeout=30): calls.append(params); return responses.pop(0)
    monkeypatch.setattr(module, "get_json", fake_get_json); client = OpenAlexClient(api_key="test"); out = client.list_recent_field_works("2026-08-11", "2026-08-18", max_records=10); assert [x.openalex_id for x in out] == ["W1", "W2"]; assert "topics.field.id:28|32" in calls[0]["filter"]; assert calls[0]["cursor"] == "*"; assert calls[1]["cursor"] == "next"

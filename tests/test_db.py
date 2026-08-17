from neuro_digest.db import LiteratureRepository
from neuro_digest.models import AuthorRef, Candidate, SourceRecord


class FakeAPI:
    def __init__(self):
        self.tables = {"papers": [], "paper_identifiers": [], "paper_sources": [], "authors": [], "paper_authors": []}; self.counter = 0
    def _id(self): self.counter += 1; return str(self.counter)
    def select_one(self, table, column, value): return self.select_one_where(table, {column: value})
    def select_one_where(self, table, filters): return next((row for row in self.tables[table] if all(row.get(k) == v for k, v in filters.items())), None)
    def insert(self, table, row):
        stored = dict(row); stored.setdefault("id", self._id()); self.tables[table].append(stored); return stored
    def update(self, table, row_id, changes):
        row = next(row for row in self.tables[table] if row.get("id") == row_id); row.update(changes); return row
    def upsert(self, table, row, *, on_conflict):
        columns = on_conflict.split(","); existing = next((x for x in self.tables[table] if all(x.get(c) == row.get(c) for c in columns)), None)
        if existing: existing.update(row); return existing
        return self.insert(table, row)
    def rpc(self, function, args):
        assert function == "merge_papers"; keep_id, remove_id = args["keep_id"], args["remove_id"]
        for table in ("paper_identifiers", "paper_sources", "paper_authors"):
            for row in self.tables[table]:
                if row.get("paper_id") == remove_id: row["paper_id"] = keep_id
        self.tables["papers"] = [x for x in self.tables["papers"] if x.get("id") != remove_id]; return keep_id


def candidate():
    return Candidate(title="A paper", doi="10.1000/ABC", authors=[AuthorRef(name="Ada Lovelace", orcid="0000-0000-0000-000X")], sources=[SourceRecord("crossref", "10.1000/abc", "https://api.crossref.org/works/10.1000/abc")])


def test_persist_is_idempotent_for_paper_source_author_and_identifiers():
    api = FakeAPI(); repo = LiteratureRepository(api); repo.persist(candidate()); repo.persist(candidate()); assert len(api.tables["papers"]) == 1; assert len(api.tables["paper_identifiers"]) == 1; assert len(api.tables["paper_sources"]) == 1; assert len(api.tables["authors"]) == 1; assert len(api.tables["paper_authors"]) == 1; assert api.tables["authors"][0]["identity_key"] == "orcid:0000-0000-0000-000X"


def test_preprint_and_published_rows_are_merged_when_mapping_arrives():
    api = FakeAPI(); repo = LiteratureRepository(api)
    pre_id, *_ = repo.persist(Candidate(title="Neural dynamics under fear", doi="10.1101/2026.01.01.123", preprint_doi="10.1101/2026.01.01.123", sources=[SourceRecord("biorxiv", "10.1101/2026.01.01.123")]))
    pub_id, *_ = repo.persist(Candidate(title="A differently formatted journal title", doi="10.1038/xyz", published_doi="10.1038/xyz", sources=[SourceRecord("openalex", "W123")]))
    assert pre_id != pub_id
    merged_id, *_ = repo.persist(Candidate(title="Neural dynamics under fear", doi="10.1038/xyz", preprint_doi="10.1101/2026.01.01.123", published_doi="10.1038/xyz", sources=[SourceRecord("biorxiv_published_mapping", "10.1101/2026.01.01.123->10.1038/xyz")]))
    assert merged_id == pub_id; assert len(api.tables["papers"]) == 1
    aliases = {(x["identifier_type"], x["identifier_value"], x["paper_id"]) for x in api.tables["paper_identifiers"]}; assert ("DOI", "10.1038/xyz", pub_id) in aliases; assert ("DOI", "10.1101/2026.01.01.123", pub_id) in aliases

from neuro_digest.social_resolver import SocialPaperResolver


class FakeSocial:
    def __init__(self): self.resolved = []; self.signals = []
    def paper_for_identifier(self, kind, value): return "paper-1" if (kind, value) == ("DOI", "10.1000/existing") else None
    def paper_for_title_key(self, title_key): return None
    def mark_link_resolved(self, link_id, paper_id, *, doi=None, pmid=None): self.resolved.append((link_id, paper_id, doi, pmid))
    def events_for_post(self, post_uri): return [{"post_uri": post_uri, "actor_did": "did:plc:actor", "signal_type": "POST", "signal_timestamp": "2026-08-17T12:00:00Z"}]
    def create_paper_signal(self, paper_id, event): self.signals.append((paper_id, event))
    def mark_link_unresolved(self, *args, **kwargs): raise AssertionError("should resolve")


def test_existing_identifier_resolves_without_external_retrieval():
    social = FakeSocial(); resolver = SocialPaperResolver.__new__(SocialPaperResolver); resolver.social = social; resolver.literature = object(); resolver.openalex = None; resolver.crossref = None; resolver.europe_pmc = None
    paper_id = resolver.resolve_link({"id": "link-1", "post_uri": "at://did:plc:actor/app.bsky.feed.post/1", "doi": "10.1000/existing", "pmid": None, "url": None})
    assert paper_id == "paper-1"; assert social.resolved == [("link-1", "paper-1", "10.1000/existing", None)]; assert social.signals[0][0] == "paper-1"

# Neurofeed MVP architecture map

The original `neuro-paper-digest` repository was a single-user acquisition prototype. The implementation now separates global/shared acquisition from user-specific ranking state.

## Service boundaries

```text
GLOBAL LITERATURE                 SHARED BLUESKY
OpenAlex / bioRxiv                public follow graphs
Crossref / Europe PMC             unique DID feed cache
        │                                  │
        ▼                                  ▼
 canonical papers ◄──── social-link resolution
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
                 Supabase state
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
       user ranking          feedback/digests
       (Phase 4+)            (Phase 5+)
```

## Phase 1 — foundation

The canonical database owns users/preferences, literature, shared Bluesky data, researcher identity, digest snapshots and feedback events. RLS separates user-readable state from server-owned ingestion state.

## Phase 2 — literature

Implemented:

- global recent OpenAlex Neuroscience/Psychology acquisition;
- bioRxiv Neuroscience preprints + publication mappings;
- Crossref and Europe PMC enrichment;
- structured authors and provenance;
- persistent DOI/OpenAlex/PMID aliases;
- historical paper merging when later provenance proves two rows equivalent;
- DB-first idempotent persistence.

The prototype per-user acquisition config and monolithic pipeline were removed.

## Phase 3 — Bluesky

### Follow synchronization

A user profile stores a human-readable handle but synchronization resolves it to a stable DID. The complete public follow list is fetched before `replace_user_bluesky_follows` atomically marks removed follows inactive and current follows active. No partial API result mutates the graph.

### Unique-account scheduling

`get_stale_bluesky_accounts` returns distinct account rows only when at least one active user follows that DID. Therefore User A, B and C following researcher X still produce one feed fetch for X. Unfollowed accounts can remain cached but are no longer scheduled.

### Social event model

An AppView author-feed item is decomposed into:

1. the underlying `bluesky_posts` object;
2. a `bluesky_post_events` actor action (`POST`, `REPOST`, `QUOTE`) with the action timestamp;
3. zero or more normalized `bluesky_scholarly_links`.

A recent repost of an old post uses the repost timestamp as the network-attention time while preserving the original post object/author. Quote posts remain intrinsic quote objects. Only posts exposing supported scholarly evidence are persisted in the MVP.

### Durable resolution

`bluesky_scholarly_links` is deliberately separate from `paper_social_signals`. Resolution order is:

1. canonical DOI/PMID already present in `paper_identifiers`;
2. DOI/PMID discovered from publisher-page metadata;
3. exact normalized-title match when metadata provides a title;
4. structured OpenAlex/Crossref/Europe PMC retrieval and canonical paper persistence;
5. otherwise retain the link as unresolved for retry.

After resolution, each actor event attached to that post becomes an idempotent `paper_social_signals` row.

## Job boundaries

1. `sync_literature` — implemented.
2. `sync_user_follow_graphs` — implemented.
3. `sync_bluesky_accounts` — implemented.
4. `resolve_social_papers` — implemented.
5. `resolve_researcher_identities` — later/minimal support as needed.
6. `embed_new_papers` — Phase 4.
7. `generate_weekly_digests` — Phase 6.
8. `send_weekly_digests` — Phase 6.

GitHub Actions remains sufficient for the lab MVP. No streaming/firehose infrastructure is introduced before pilot evidence demands it.

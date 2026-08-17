# Neurofeed MVP architecture map

## Current boundaries through Phase 4

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
             embeddings + features
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      semantic      network      broad
      candidates    candidates   candidates
          └────────────┼────────────┘
                       ▼
               decomposed ranking
                       │
             focused / broad lanes
                       ▼
              digest layer (next)
```

## Candidate retrieval

`match_papers` performs service-only HNSW cosine nearest-neighbour retrieval over recent canonical papers. `get_user_network_candidates` derives social features from active user follows and high-confidence followed-author mappings. `get_broad_candidates` returns deliberately important broader candidates using configured priority venues and early citation signal.

Previously seen papers are hard-suppressed through `get_user_seen_papers` before final scoring.

## Embedding lifecycle

- model: `text-embedding-3-small`;
- dimensionality: 1536;
- paper input: title + abstract + venue;
- declared profile input: free-text research description;
- SHA-256 input hashes prevent unnecessary regeneration;
- paper text changes invalidate the stored embedding automatically;
- HNSW cosine index lives on non-null paper embeddings only.

## User representation

The MVP separates declared and learned state:

- `declared_embedding` — explicit research description;
- `learned_positive_embedding` — Phase 5 behavioral positive centroid;
- `learned_negative_embedding` — Phase 5 negative centroid;
- `user_preference_features` — interpretable METHOD/SPECIES/etc. weights.

A deterministic taxonomy extracts initial inferred method/species features without using an LLM. Manually declared and learned features are not deleted when inferred features refresh.

## Ranking v1

Every ranked paper preserves components:

- semantic;
- Bluesky;
- method/species fit;
- priority/quality prior;
- broad-discovery importance;
- novelty;
- recency;
- provenance including followed-actor counts and followed-author state.

The Bluesky score saturates independent network sources, weights quotes/direct posts more than reposts, decays old discussion, and combines discussion with the followed-author signal without allowing raw volume to grow linearly without bound.

The final broad lane is selected separately according to the user's discovery balance, so serendipity is intentional rather than a low-score fallback.

## Job boundaries

1. `sync_literature` — implemented.
2. `sync_user_follow_graphs` — implemented.
3. `sync_bluesky_accounts` — implemented.
4. `resolve_social_papers` — implemented.
5. `embed_new_papers` — implemented.
6. `refresh_user_models` — implemented.
7. feedback learning — Phase 5.
8. `generate_weekly_digests` — Phase 6.
9. `send_weekly_digests` — Phase 6.

The ranking code remains deterministic/interpretable except for the embedding representation. No trained recommender model is introduced before pilot evidence warrants it.

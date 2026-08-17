# Neurofeed MVP architecture map

## State flow through Phase 5

```text
GLOBAL LITERATURE + SHARED BLUESKY
                ↓
         canonical papers
                ↓
     embeddings + user profile
                ↓
       decomposed ranking
                ↓
      future digest snapshot
                ↓
        user interactions
                ↓
 append-only user_paper_events
                ↓
 effective feedback reduction
        ┌───────┴────────┐
        ▼                ▼
positive/negative     signed learned
semantic centroids    method/species features
        └───────┬────────┘
                ▼
          future ranking
```

## Feedback semantics

The raw event stream is never rewritten. `get_effective_paper_feedback` deterministically reduces each user-paper history:

- CLICK contributes once as a weak positive;
- only the latest SAVE/UNSAVE state contributes;
- only the latest MORE_LIKE_THIS/LESS_LIKE_THIS action contributes;
- a Less reason configured as neutral (initially `already_knew_it`) does not generate negative preference learning;
- IMPRESSION has no preference weight but still supports exposure history and evaluation.

This makes the learned representation reproducible from events and prevents accidental multiplication of repeated clicks/saves.

## Learned user model

Positive and negative effective papers produce separate weighted normalized embedding centroids. The job also extracts configured interpretable features from those papers and aggregates signed feature weights. Rebuilding with no effective feedback explicitly clears stale learned vectors/features.

The declared profile is never overwritten. Phase 4's feedback maturity ramp controls how much the learned positive centroid affects semantic similarity and how strongly the negative centroid suppresses candidates.

## Save state

`user_saved_papers` is a `security_invoker` view over the append-only event table. RLS on `user_paper_events` therefore remains the ownership boundary.

## Implemented job boundaries

1. global literature sync;
2. user follow graph sync;
3. shared unique-DID Bluesky sync;
4. social-paper resolution;
5. paper embedding refresh;
6. declared user model refresh;
7. learned feedback model refresh;
8. transparent rank preview.

Phase 6 adds digest generation and delivery without changing these ingestion/learning boundaries.

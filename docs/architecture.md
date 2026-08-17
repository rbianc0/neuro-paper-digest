# Neurofeed MVP architecture through Phase 6

```text
literature APIs ───────┐
                       ├─> canonical papers ─> embeddings ─┐
public Bluesky network ┘                                   │
                                                           ├─> transparent ranking
user declared profile ─────────────> user model ───────────┤
feedback events ──> learned positive/negative model ───────┘
                                                           │
                                                           ▼
                                                  immutable digest snapshot
                                                           │
                                      ┌────────────────────┼──────────────────┐
                                      ▼                    ▼                  ▼
                                  HTML/text           interaction tokens    email send
                                      │                    │                  │
                                      └───────────── Phase 7 routes ──────────┘
```

## Digest reproducibility

`digests` stores subject, rendered HTML/text, content hash, delivery state and provider ID. `digest_items` stores exactly one paper per digest with rank, section, all decomposed score components, summary, deterministic why-explanation, paper URL, summary model/input hash, and provenance snapshot.

A unique `(user_id, period_start, period_end, version)` key prevents silent regeneration. Delivery uses the digest ID as the provider idempotency key.

## Interaction security

`interaction_tokens` stores only SHA-256 hashes of cryptographically random URL tokens. The table and lookup/consume RPCs are service-only. Action-token inspection is non-consuming; redemption requires the caller to provide the expected action. This supports a safe GET confirmation page followed by an explicit POST for state-changing Save/More/Less actions.

CLICK tokens are deliberately non-single-use because article redirects may be revisited. The feedback reducer counts CLICK only once per paper, so repeated visits do not multiply learning weight.

## Summary boundary

The LLM receives only canonical title/authors/venue/date/abstract data already present in Neurofeed and returns a strict structured `{paper_id, summary}` result. Missing abstracts use a deterministic fallback rather than inviting unsupported summarization. Bibliographic existence and identity remain exclusively structured-data concerns.

## Remaining MVP phases

- Phase 7: lightweight Next.js web application and interaction endpoints.
- Phase 8: researcher identity resolution + Scientists Worth Knowing.
- Phase 9: lab pilot/instrumentation and tuning.

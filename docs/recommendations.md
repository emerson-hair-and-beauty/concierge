# Recommendations

Two genuinely separate features share the name "recommendations" in this
codebase. Don't conflate them.

## 1. Product search (live, widely used)

`app/agents/recommendation/lib/knowledge_base/query_products.py`'s
`query_products()` embeds a text query and searches a Pinecone index for
matching products. This is live and used by several different callers:

- The web chat agents that are actually wired to `/api/web/chat` —
  `discovery_agent.py`, `faq_agent.py`, `hair_advisor_agent.py` (see
  [`chat-orchestration.md`](chat-orchestration.md))
- `POST /search/products` (`app/api/search.py`)
- `app/agents/recommendation/lib/create_recommendations.py`'s
  `createRecommendations()`, which turns each step of a generated routine
  into a product query — used by the quiz-based routine generator
  (`app/agents/orchestrator.py`, see `chat-orchestration.md`)
- The not-live decision-state pipeline and `response_handlers.py`

**Ingestion:**
`app/agents/recommendation/lib/knowledge_base/index_product_matrix.py`
reads the "Summary" sheet of
`Emerson Product Matrix_Master_File_Updated (1).xlsx` at the repo root and
re-indexes the entire Pinecone index from it (full replace, not an
incremental update). `create_json_knowledge_base.py` and
`embed_knowledge_base.py` are earlier/alternative steps in the same
ingestion job — check which one is actually current before relying on
either; this doc does not resolve that.

## 2. Adaptive nudges (live, unrelated to product search)

`app/services/recommendations/recommendation_agent.py`'s
`generate_recommendations()` is a single LLM call that reads a user's
current routine, their last 3 unread alerts, and a vitals summary, and
returns 2-3 short nudges (`{title, message, reasoning, routine_step_ref,
recommendation_type}`). This is what powers `GET /api/recommendations/{user_id}`
(`app/api/recommendations.py`). It does not search Pinecone and does not
share code with `query_products()` — it is a distinct feature that happens
to use the same word.

## Push notifications

`app/services/recommendations/push_service.py` stores Web Push
subscriptions (endpoint + encryption keys) in Supabase and sends
notifications via `pywebpush`. Wired to `POST /api/push/subscribe` and
`DELETE /api/push/subscribe` in `app/api/recommendations.py`. Setup details
are in `PUSH_NOTIFICATIONS_SETUP.md`.

# Letta live deployment (M15A)

How the `letta` memory backend runs for real: one self-hosted Letta server plus
a local Ollama service for embeddings. Everything is launched from
`docker-compose.letta.yml` and configured from `.env` (see `.env.example`);
no secrets are hardcoded anywhere.

## Server version and image

* Image: `letta/letta:0.16.8` (DockerHub `:latest` currently points at 0.16.8;
  pinned here for reproducibility). Health probe: `GET /v1/health/`.
* Client: `letta-client` 1.12.1 (installed in the repo venv). Verified live:
  agent create / archival passage create / search / delete all work against
  this server version.
* Note: the current Letta docs state the open-source Docker image is no longer
  an actively supported product surface; it remains the documented way to
  self-host the v1 API that `letta-client` targets.

## Docker architecture

Two services (`docker compose -f docker-compose.letta.yml up -d`):

* `letta-server` — the Letta API server. The image **embeds PostgreSQL 15 +
  pgvector**, so no external database container and no `LETTA_PG_URI` are
  needed; a named volume on `/var/lib/postgresql/data` persists the database.
* `letta-ollama` — `ollama/ollama` that pulls and serves the embedding model.
  Its own entrypoint is `ollama`, so the compose file overrides it with a shell
  that serves and pulls on startup, and its healthcheck only turns healthy once
  the model is present (the letta server `depends_on: service_healthy`).

## Provider / embedding configuration

* **LLM (DeepSeek, OpenAI-compatible)** — the benchmark planner already uses
  DeepSeek via `.env` `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`. Compose maps
  those straight into the Letta server as `OPENAI_API_KEY` / `OPENAI_BASE_URL`
  (Letta's OpenAI-compatible provider), so `.env` needs no duplication. DeepSeek
  advertises `deepseek-v4-flash`, which Letta registers under the
  `openai-proxy/` handle prefix.
* **Embeddings (Ollama `nomic-embed-text`)** — DeepSeek has **no embeddings
  API** (404 verified), so embeddings come from the bundled Ollama service, an
  officially documented Letta provider. The small `nomic-embed-text` model keeps
  everything self-hosted and offline-capable.

## Memory-only usage contract

Letta agents in this benchmark **never run inference**. The server-side defaults
`LETTA_DEFAULT_LLM_HANDLE` and `LETTA_DEFAULT_EMBEDDING_HANDLE` exist only so
the adapter's `name`-only agent creation validates; the DeepSeek model is never
called for generation. The `LettaBackend` adapter is unchanged: it still goes
through `MemoryBackend` (one agent per episode, archival-memory passages only),
and `scripts/verify_letta_live.py` drives the real adapter through that
interface (add/retrieve/update/reset; SKIPs with exit 0 when offline).

## Limitations encountered

* **Agent creation demands model + embedding** on a Docker server (docs:
  "required when using Docker"). Handled without touching the adapter via the
  server's official `default_llm_handle` / `default_embedding_handle` settings —
  note these are fields of Letta's main `Settings` class, which reads env vars
  with a `letta_` prefix, so the compose vars are `LETTA_DEFAULT_*`.
* **`OLLAMA_BASE_URL` needs the `/v1` suffix.** The server stores the value
  verbatim as the embedding base URL and calls `<base_url>/embeddings` on
  insert; without `/v1` Ollama returns 404. The Ollama provider's own
  `list_embedding_models_async` still hits the native `/api/...` endpoints
  correctly (it strips `/v1` internally).
* **Embedding handle carries the `:latest` tag** (`ollama/nomic-embed-text:latest`)
  because Ollama's `/api/tags` reports tagged names; the default handle must
  match exactly.
* **`openai-proxy/` handle prefix.** Any custom `OPENAI_BASE_URL` registers
  models as `openai-proxy/<model>`, which is what the LLM default handle uses.
  Upstream reports (letta-ai/letta #3224, #3278) note the proxy `base_url` can
  fail to propagate to an agent's stored LLM config on some versions — harmless
  here because agents never run inference.
* **Unusable built-in embedding entries.** The openai provider also registers
  `openai/text-embedding-*` defaults that point at DeepSeek; those 404 and must
  not be used. All passages use the Ollama embedding.
* **Adapter-level constraints (unchanged, documented in the adapter docstring):**
  no metadata on archival insert (event_id is prefixed into the text), no
  in-place passage update (`update()` deletes + re-inserts), and the agent-scoped
  archival search returns no relevance score (`MemoryItem.score` stays `None`).

## Verification

```
.venv/Scripts/python scripts/verify_letta_live.py
```

Prints PASS for checks A (add then retrieve), B (update reflects the new
location), C (reset isolates a fresh episode) against the live server, and exits
non-zero on any failure; prints SKIP and exits 0 when the server is unreachable.

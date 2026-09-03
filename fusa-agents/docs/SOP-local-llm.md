# SOP — Running the FuSa Agent Framework with Alternate LLM Backends

**Document ID:** SOP-LLM-001 · **Rev:** 1.3 · **Date:** 2026-09-01 · **Owner:** FuSa framework maintainer

## 1. Purpose

Run the full FuSa agent chain (author → gate → independent review → status board) against an
**alternate LLM backend** instead of the default Anthropic cloud API:

- a **locally hosted LLM** (Ollama, LM Studio, vLLM, llama.cpp) — for offline work,
  data-residency constraints, or zero-cost experimentation;
- **Grok (xAI cloud API)** — selected with an xAI API key;
- **Groq (GroqCloud)** — fast hosted open-weight models, selected with a Groq API key;
- **OpenAI** — GPT models, selected with an OpenAI API key; or
- **Gemini (Google)** — selected with a Gemini/Google API key.

> **Grok ≠ Groq.** Grok is xAI's model family (keys `xai-…`); Groq is GroqCloud's fast
> inference service for open-weight models (keys `gsk_…`). They are separate providers here.

## 2. Scope

Applies to all `python -m fusa` commands that call a model (`run`, `run-all`). Commands that are
deterministic (`plan`, `gate`, `metrics`, `status`, `aspice`, `report`, `template`, ReqIF
import/export) never call an LLM and are unaffected.

## 3. How it works (no code changes)

`fusa/agents/llm.py` instantiates `anthropic.Anthropic()` with no arguments. The Anthropic Python
SDK resolves its endpoint and credentials from the environment:

| Variable | Effect |
|---|---|
| `FUSA_PROVIDER` | `anthropic` (default), `grok`, `groq`, `openai` or `gemini` — selects the backend in `fusa/agents/llm.py` |
| `ANTHROPIC_BASE_URL` | Points the SDK at any server exposing the Anthropic Messages API (`POST /v1/messages`) |
| `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`) | Credential for `anthropic` provider — local servers accept a dummy value |
| `XAI_API_KEY` (or `GROK_API_KEY`) | Credential for the `grok` provider |
| `GROQ_API_KEY` | Credential for the `groq` provider (GroqCloud, OpenAI-compatible API) |
| `OPENAI_API_KEY` | Credential for the `openai` provider |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | Credential for the `gemini` provider |
| `FUSA_MODEL` | Model name passed in the request (local tag, `grok-4.6`, `gpt-5.6`, `gemini-3.1-pro`, …) |
| `FUSA_MAX_TOKENS` | Response budget (default 6000) |

Supported paths:

- **Option A — Ollama (recommended local):** Ollama ≥ 0.14 natively serves `/v1/messages`.
- **Option B — LM Studio / vLLM / llama.cpp via LiteLLM proxy:** for OpenAI-compatible-only
  servers, put a LiteLLM proxy in front; it translates `/v1/messages` to the backend.
- **Option C — Grok (xAI):** xAI's API is Anthropic-SDK-compatible at `https://api.x.ai`;
  the built-in `grok` provider targets it directly (§7).
- **Option D — Groq (GroqCloud):** OpenAI-compatible API at `https://api.groq.com/openai/v1`;
  the built-in `groq` provider calls it directly — no proxy needed (§8).
- **Options E/F — OpenAI and Gemini:** same OpenAI-style path, built in — `openai` targets
  `https://api.openai.com/v1`, `gemini` targets Google's OpenAI-compatible endpoint (§9).

Provider, model and API key can also be set at runtime in the dashboard (`fusa ui` → **⚙ LLM**),
without touching the environment (§7.2 — same panel for every provider).

**Setting the key once (`.env`).** Instead of exporting variables every session, copy
`.env.example` to `.env` in `fusa-agents/` and fill in the provider and key:

```
FUSA_PROVIDER=grok
XAI_API_KEY=xai-...
```

Every `fusa` command picks it up. A real environment variable always wins over the file, and
`.env` is gitignored — but it is a plaintext key in your working tree, so treat it accordingly
and never copy it into a shared machine or an image.

## 4. Prerequisites

- macOS / Linux machine with ≥ 16 GB RAM (≥ 32 GB or an Apple-silicon GPU recommended for 14B+ models).
- Python ≥ 3.10 and this repo installed: `pip install -e ".[dev]"` from `fusa-agents/`.
- No network access to `api.anthropic.com` is required once the model is pulled.

## 5. Procedure — Option A: Ollama (native Anthropic endpoint)

### 5.1 Install and start Ollama

```bash
brew install ollama          # or: curl -fsSL https://ollama.com/install.sh | sh   (Linux)
ollama --version             # must be >= 0.14 for /v1/messages support
ollama serve                 # if not already running as a service
```

### 5.2 Pull a model

Authoring work products needs strong instruction-following and long context. Recommended:

```bash
ollama pull qwen3:14b        # good quality/size balance
# alternatives: llama3.1:8b (lighter), qwen3:32b / gpt-oss:20b (better, needs more RAM)
```

Use a model/context configuration of **at least 32K tokens** — agent prompts are assembled from
clause, method, convention and checklist registers plus upstream work products, and are long.
Raise the context window and keep the model loaded between agent runs:

```bash
OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_KEEP_ALIVE=60m ollama serve
```

### 5.3 Point FuSa at Ollama

```bash
export ANTHROPIC_BASE_URL=http://localhost:11434
export ANTHROPIC_API_KEY=ollama          # required by the SDK, ignored by Ollama
export FUSA_MODEL=qwen3:14b              # must match the pulled tag exactly
export FUSA_MAX_TOKENS=6000
unset FUSA_DRY_RUN                       # dry-run would bypass the model entirely
```

### 5.4 Verify the endpoint before running the chain

```bash
curl -s http://localhost:11434/v1/messages \
  -H "content-type: application/json" -H "x-api-key: ollama" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"qwen3:14b","max_tokens":50,"messages":[{"role":"user","content":"Say READY"}]}'
```

Expected: a JSON response whose `content[0].text` contains `READY`. Do not proceed until this passes.

### 5.5 Run the chain

```bash
cd fusa-agents
python -m fusa plan                # creation order (no LLM)
python -m fusa run sys-hara        # single agent first — cheap smoke test of the local model
python -m fusa status
python -m fusa run-all             # full chain
python -m fusa report --asil B
```

## 6. Procedure — Option B: OpenAI-compatible server behind LiteLLM

For LM Studio, vLLM, or llama.cpp `llama-server` (these expose `/v1/chat/completions`, not
`/v1/messages`):

```bash
pip install 'litellm[proxy]'

cat > litellm-local.yaml <<'YAML'
model_list:
  - model_name: local-model
    litellm_params:
      model: openai/<served-model-name>          # e.g. openai/qwen3-14b
      api_base: http://localhost:1234/v1          # LM Studio default; vLLM: 8000
      api_key: none
YAML

litellm --config litellm-local.yaml --port 4000
```

Then:

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_API_KEY=sk-local                # any value unless you set a LiteLLM master key
export FUSA_MODEL=local-model
```

Verify with the same `curl` as §5.4 (against port 4000), then run §5.5.

## 7. Procedure — Option C: Grok (xAI cloud API)

> Not a local backend: prompts and work-product content are sent to xAI's cloud.
> Confirm this is acceptable under your project's confidentiality rules before use.

### 7.1 Via environment variables (CLI runs)

1. Create an API key in the xAI console (https://console.x.ai) and fund/verify the account.
2. Export:

```bash
export FUSA_PROVIDER=grok
export XAI_API_KEY=xai-...               # or GROK_API_KEY
export FUSA_MODEL=grok-4.6               # default; grok-4-fast is the cheap/long-context option
unset FUSA_DRY_RUN
```

3. Verify the endpoint:

```bash
curl -s https://api.x.ai/v1/messages \
  -H "content-type: application/json" -H "x-api-key: $XAI_API_KEY" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"grok-4.6","max_tokens":50,"messages":[{"role":"user","content":"Say READY"}]}'
```

4. Run the chain as in §5.5.

Current model IDs and pricing: https://docs.x.ai/developers/models. `ANTHROPIC_BASE_URL` is not
used by the `grok` provider (override the endpoint with `FUSA_GROK_BASE_URL` if ever needed).

### 7.2 Via the dashboard (⚙ LLM settings)

1. `python -m fusa ui` and open http://127.0.0.1:8000.
2. Click **⚙ LLM** in the header.
3. Provider → **Grok (xAI)** (the model field pre-fills with `grok-4.6`; edit if needed).
4. Paste the API key and click **Save**, then **Test connection** — expect “✓ backend reachable”.
5. Run agents / **▶ Run all** as usual. The header badge shows `grok · <model>`.

Key handling: the key is held in server process memory only — never written to disk and never sent
back to the browser. After a server restart, re-enter it (or set `XAI_API_KEY` so it is picked up
automatically). The backend cannot be changed while a run is in progress (HTTP 409).

## 8. Procedure — Option D: Groq (GroqCloud, fast open-weight models)

> Also a cloud backend: prompts and work-product content are sent to GroqCloud.
> Confirm this is acceptable under your project's confidentiality rules before use.

### 8.1 Via environment variables (CLI runs)

1. Create an API key at https://console.groq.com (keys start with `gsk_`).
2. Export:

```bash
export FUSA_PROVIDER=groq
export GROQ_API_KEY=gsk_...
export FUSA_MODEL=openai/gpt-oss-120b    # default; openai/gpt-oss-20b is the lighter option
unset FUSA_DRY_RUN
```

3. Verify the endpoint:

```bash
curl -s https://api.groq.com/openai/v1/chat/completions \
  -H "content-type: application/json" -H "authorization: Bearer $GROQ_API_KEY" \
  -d '{"model":"openai/gpt-oss-120b","max_tokens":50,"messages":[{"role":"user","content":"Say READY"}]}'
```

4. Run the chain as in §5.5.

Current model IDs: https://console.groq.com/docs/models (Groq has deprecated its Llama chat
models — use the `openai/gpt-oss-*` models for general-purpose work). The endpoint can be
overridden with `FUSA_GROQ_BASE_URL`. Note Groq speaks the **OpenAI** chat-completions API,
not the Anthropic one — the `groq` provider handles that internally; `ANTHROPIC_BASE_URL`
is not involved.

### 8.2 Via the dashboard

Same panel as §7.2: **⚙ LLM** → provider **Groq (GroqCloud — fast open models)** (model
pre-fills with `openai/gpt-oss-120b`) → paste the `gsk_…` key → **Save** → **Test connection**.
The same key-handling rules apply: memory only, never on disk, never echoed back.

## 9. Procedure — Options E & F: OpenAI and Gemini (cloud APIs)

> Cloud backends: prompts and work-product content are sent to OpenAI / Google.
> Confirm this is acceptable under your project's confidentiality rules before use.

Identical mechanics to Groq (§8) — both are OpenAI-style chat-completions backends.

### 9.1 OpenAI

1. Create an API key at https://platform.openai.com (keys start with `sk-`).
2. Export and run:

```bash
export FUSA_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export FUSA_MODEL=gpt-5.6                # default; see developers.openai.com for current IDs
unset FUSA_DRY_RUN
```

Verify, then run the chain as in §5.5:

```bash
curl -s https://api.openai.com/v1/chat/completions \
  -H "content-type: application/json" -H "authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-5.6","max_completion_tokens":50,"messages":[{"role":"user","content":"Say READY"}]}'
```

Note: GPT-5-series models take `max_completion_tokens` (not `max_tokens`) — the `openai`
provider sends the right parameter automatically. Endpoint override: `FUSA_OPENAI_BASE_URL`.

### 9.2 Gemini (Google)

1. Create an API key at https://aistudio.google.com (keys start with `AIza`).
2. Export and run:

```bash
export FUSA_PROVIDER=gemini
export GEMINI_API_KEY=AIza...            # GOOGLE_API_KEY also works
export FUSA_MODEL=gemini-3.1-pro         # default (deep reasoning); gemini-3.7-flash is the fast/cheap option
unset FUSA_DRY_RUN
```

Verify, then run the chain as in §5.5:

```bash
curl -s https://generativelanguage.googleapis.com/v1beta/openai/chat/completions \
  -H "content-type: application/json" -H "authorization: Bearer $GEMINI_API_KEY" \
  -d '{"model":"gemini-3.1-pro","max_tokens":50,"messages":[{"role":"user","content":"Say READY"}]}'
```

Endpoint override: `FUSA_GEMINI_BASE_URL`. Current model IDs: https://ai.google.dev/gemini-api/docs/models.

### 9.3 Via the dashboard

Same panel as §7.2: **⚙ LLM** → provider **OpenAI** or **Gemini (Google)** (the model field
pre-fills with the provider default) → paste the key → **Save** → **Test connection**.
Same key-handling rules: memory only, never on disk, never echoed back.

## 10. Rollback to the default Anthropic cloud API

```bash
unset ANTHROPIC_BASE_URL FUSA_PROVIDER XAI_API_KEY GROK_API_KEY GROQ_API_KEY \
      OPENAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY
export ANTHROPIC_API_KEY=<real key>
export FUSA_MODEL=claude-sonnet-5      # framework default
```

Or in the dashboard: **⚙ LLM** → provider **Anthropic** → Save.

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `anthropic.AuthenticationError` | `ANTHROPIC_API_KEY` unset — export any non-empty value for local servers |
| `404` on `/v1/messages` | Ollama < 0.14, or Option-B server hit directly without LiteLLM — upgrade or add the proxy |
| Connection refused | Server not running, or wrong port in `ANTHROPIC_BASE_URL` |
| `model not found` in response | `FUSA_MODEL` doesn't match the pulled tag (`ollama list`) / LiteLLM `model_name` |
| Gate failures, malformed IDs, empty sections | Model too small for the method prompts — move up (14B → 32B), keep `FUSA_MAX_TOKENS` ≥ 6000, ensure ≥ 32K context |
| Very slow first agent, then fast | Cold model load — set `OLLAMA_KEEP_ALIVE=60m` |
| Chain works with `FUSA_DRY_RUN=1` but not live | Dry-run never calls the model; the problem is the endpoint — re-run §5.4 |
| `provider '…' needs an API key` | Set the provider's env var (§3 table), or enter the key under **⚙ LLM** in the dashboard |
| `401` / `AuthenticationError` on a cloud provider | Key invalid or revoked — regenerate at the provider's console (x.ai / groq.com / platform.openai.com / aistudio.google.com) |
| Key gone after restarting `fusa ui` | By design (memory only) — re-enter it, or set the provider's env var |
| `model_decommissioned` / model not found on Groq | Llama chat models are deprecated — switch to `openai/gpt-oss-120b` (`console.groq.com/docs/models`) |
| `unsupported parameter: max_tokens` on OpenAI | GPT-5-series wants `max_completion_tokens` — use the `openai` provider (it sends the right one), not a custom base-URL workaround |
| Wrong provider entirely (Grok vs Groq mix-up) | `xai-…` keys belong to provider `grok`; `gsk_…` keys to provider `groq`; `sk-…` OpenAI; `AIza…` Gemini |

## 12. Quality note (functional-safety relevance)

Local open-weight models produce noticeably weaker work products than the default cloud model;
frontier cloud alternatives (Grok, OpenAI, Gemini) sit closer to it, and Groq serves open-weight
models — open-weight quality at cloud speed. Validate output quality on one work product before
committing to a full chain. The deterministic gate (`fusa/gate.py`) and the
independent `ReviewAgent` still enforce structure, ID grammar and coverage, but expect more
`gate_failed` / `rework` cycles. Treat work products from any non-default backend as
**drafts for engineering review**, not as release-ready safety evidence.

## 13. References

- [Ollama — Anthropic compatibility docs](https://docs.ollama.com/api/anthropic-compatibility)
- [Ollama blog — Claude Code with Anthropic API compatibility](https://ollama.com/blog/claude)
- [LiteLLM proxy documentation](https://docs.litellm.ai/docs/simple_proxy)
- [xAI docs — API overview, models & pricing](https://docs.x.ai/developers/models)
- [Groq docs — supported models](https://console.groq.com/docs/models) · [OpenAI compatibility](https://console.groq.com/docs/openai)
- [OpenAI API reference — chat completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [Gemini API — OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) · [models](https://ai.google.dev/gemini-api/docs/models)
- `fusa/agents/llm.py`, `fusa/config.py` — where the providers and env switches live

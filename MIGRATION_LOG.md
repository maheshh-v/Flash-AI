# Cloudflare Workers AI Migration Log
# If you are a new AI session, READ THIS ENTIRE FILE before doing anything.

---

## Project: Flashspace AI Agent Backend
**Repo:** `c:\Users\HP\ai-agent-backend-1`
**Active Branch:** `feature/cf-workers-ai` (off `main`)

---

## Goal
Replace the OpenAI proxy (`stirringminds.com`) and make Cloudflare Workers AI
the **primary** LLM provider. FastAPI, MongoDB, Redis, and Pinecone all stay on VPS.
Google Gemini remains as automatic fallback.

**Focus roles: Guest (public) and Admin.**

---

## Cloudflare Credentials
| Field               | Value |
|---------------------|-------|
| CF_API_TOKEN        | `cfut_7gfchyouYakB9KNqjDTRRwoEJTeVndUojt6XIu6uf0047fc1` |
| CF_GATEWAY_URL      | `https://gateway.ai.cloudflare.com/v1/d2ab95608d255a1cbfac7fc59c557989/mahesh-flashspace/workers-ai` |
| CF_MODEL            | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |

### Correct `base_url` for `ChatOpenAI` (langchain-openai):
```
https://gateway.ai.cloudflare.com/v1/d2ab95608d255a1cbfac7fc59c557989/mahesh-flashspace/workers-ai/
```
langchain-openai appends `/chat/completions` automatically.
Model goes in the `model=` parameter as `@cf/meta/llama-3.3-70b-instruct-fp8-fast`.

---

## Architecture Decisions (DO NOT CHANGE WITHOUT DISCUSSION)
1. **app/llm.py priority**: CF Workers AI → Google Gemini → Offline stub
2. **Embeddings** (`app/vectorstore.py`): Stay on Google Gemini (`text-embedding-004`) — do NOT change, Pinecone index was built with these vectors
3. **app/embedding_client.py**: Was pointing to old proxy. Now redirected to Google Gemini embedding REST API to maintain vector consistency for Partner Pinecone query
4. **No serverless migration**: The FastAPI server does NOT move to Cloudflare Workers. Only inference changes.
5. **`with_structured_output(method="json_mode")`**: Used in `safety_guard.py` and `router.py`. CF gateway supports JSON mode via OpenAI-compatible API — verified via docs.

---

## File Change Map
| File               | Status     | Change Description |
|--------------------|------------|-------------------|
| `.env`             | ✅ Done    | Added CF_API_TOKEN, CF_GATEWAY_URL, CF_MODEL. Commented out PROXY_URL/EMBEDDING_URL/CHAT_URL |
| `app/llm.py`       | ✅ Done    | New priority: CF first, Gemini second, offline third |
| `app/embedding_client.py` | ✅ Done | Points to Google Gemini embedding API; no longer uses old proxy |
| `MIGRATION_LOG.md` | ✅ Done    | This file |

---

## Test Status
| Test                        | Status  | Notes |
|-----------------------------|---------|-------|
| Raw curl to CF gateway      | ⏳ Pending | Run: see test section below |
| Guest agent smoke test      | ⏳ Pending | |
| Admin agent smoke test      | ⏳ Pending | |
| Safety guard structured output | ⏳ Pending | |
| Branch pushed to origin     | ⏳ Pending | |

---

## Raw Curl Test (run this first to confirm credentials)
```powershell
curl -X POST `
  "https://gateway.ai.cloudflare.com/v1/d2ab95608d255a1cbfac7fc59c557989/mahesh-flashspace/workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast" `
  -H "Authorization: Bearer cfut_7gfchyouYakB9KNqjDTRRwoEJTeVndUojt6XIu6uf0047fc1" `
  -H "Content-Type: application/json" `
  -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Reply with: CF_OK\"}],\"max_tokens\":20}'
```

---

## Open Questions / Risks
- If CF gateway enforces rate limits mid-request, the Gemini fallback auto-kicks in
- Llama 3.3 70B prompt format differs slightly from GPT — monitor response quality on first production test
- Partner agent not prioritized in this session — works but not specifically tested

---

## Next Steps (if session ends here)
1. Run the curl test above
2. Start the FastAPI server: `uvicorn app.main:app --reload`
3. Call `/chat` with no auth (guest) and with admin JWT
4. Check server logs for `[LLM Provider] Cloudflare Workers AI` message
5. Push branch: `git push origin feature/cf-workers-ai`
6. Merge to `main` only after user confirms tests pass

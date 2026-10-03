# Jev Proxy

A drop-in proxy for the [TypeSafe Jev API](https://api.typesafe.ai/docs).
You keep your TypeSafe key on the server. Other people get **proxy keys** from you and call
the proxy with **the same requests and responses** as the real API. Only the base URL and key change.

```
participant ──(jvp_ key)──▶  jev-proxy  ──(your apikey_ key)──▶  api.typesafe.ai
                              │ checks key, limits, budget
                              │ logs usage per key
                              │ passes the answer back unchanged
```

| Direct to TypeSafe | Through your proxy |
|---|---|
| `https://api.typesafe.ai/v1/systemone` | `https://your-proxy.example.com/v1/systemone` |
| `Authorization: Bearer apikey_...` | `Authorization: Bearer jvp_...` |

All `/v1/*` endpoints are forwarded: `POST /v1/systemone` and `GET /v1/models`.
(`/api/v1/...` works too, for clients that expect an `/api` prefix.)

## Quick start

No dependencies. Node 18.17+.

```bash
cd proxy
cp .env.example .env            # put your real JEV_API_KEY in .env
npm run keys -- --count 30 --prefix team --max-cost 0.50 \
  --expires 2026-10-02 --base-url https://your-proxy.example.com
npm start
```

`npm run keys` writes:

- `keys.json`: only SHA-256 hashes of the keys (safe-ish to keep on the server)
- `keys-handout.csv` and `keys-handout.html`: the plain keys, once. Print the HTML as cards for a workshop.

Keys reload automatically when `keys.json` changes. Disable a key by setting `"enabled": false`.

### Rehearse without spending money

```bash
npm run mock      # MOCK_UPSTREAM=1: a local fake Jev answers /v1/systemone and /v1/models
```

The mock uses keyword matching. It has the right shape, not real intelligence. Its validation
copies the real API: `test/fixtures/systemone-cases.json` holds 39 requests recorded from
`api.typesafe.ai` (good ones and every kind of 400/422 error), and the tests check that the mock
answers each one with the same status, the same error body and the same answer fields.

## Call it

```bash
curl https://your-proxy.example.com/v1/systemone \
  -H "Authorization: Bearer $JEV_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-latest",
    "state": "Customer: my bubble tea order is 40 minutes late!",
    "questions": {
      "angry": { "type": "noul", "instructions": "Is the customer upset?" }
    }
  }'
# -> {"model":"jev-1.13.0","answers":{"angry":{"type":"noul","noul":0.97}},"usage":{"input_tokens":287,"output_tokens":21}}
```

`"model"` is required (`jev-latest` or `jev-preview`; `GET /v1/models` lists them).

### The official SDKs work unchanged

Point them at the proxy with their own environment variables. Tested with
`typesafe-sdk` 0.7.2 (Python) and `@typesafe-ai/sdk` 0.6.0 (JavaScript), against the real API:

```bash
export TYPESAFE_BASE_URL=https://your-proxy.example.com
export TYPESAFE_API_KEY=jvp_...        # the proxy key, not your TypeSafe key
```

```python
from typesafe_sdk import TypeSafeClient

with TypeSafeClient() as client:
    r = client.system_one(state="My tea is 40 minutes late!",
                          questions={"angry": {"type": "noul", "instructions": "Is the customer upset?"}})
```

Their retries (429, 529, 5xx with `retry-after` / `retry-after-ms`) and `request_id` work too,
because the proxy passes those headers on.

Python, no SDK needed:

```python
import json, os, urllib.request

req = urllib.request.Request(
    os.environ["JEV_BASE_URL"] + "/v1/systemone",
    data=json.dumps({"model": "jev-latest", "state": "...", "questions": {...}}).encode(),
    headers={"Authorization": "Bearer " + os.environ["JEV_API_KEY"],
             "Content-Type": "application/json"},
)
print(json.load(urllib.request.urlopen(req)))
```

## What the proxy does

| Feature | Detail |
|---|---|
| Key swap | Caller's `Authorization` (or `x-api-key`) is checked, then replaced with your `JEV_API_KEY`. Cookies and other headers are not forwarded. |
| Same protocol | Status codes and JSON bodies from TypeSafe are passed through byte for byte (including `422` validation errors and `529 Overloaded`). The `x-typesafe-request-id`, `retry-after` and `retry-after-ms` headers are passed on; other upstream headers (cookies, `server`) are not. |
| Rate limit | Per key, requests per minute. `429` + `Retry-After`, `error_type: "rate_limit_error"`. |
| Daily limit | Per key, requests per day in `TIME_ZONE`. `429`, `error_type: "rate_limit_error"`. |
| Budget | Per key `max_cost_usd`. Cost = `usage.input_tokens` × `INPUT_PRICE_PER_MILLION` (TypeSafe: US$0.042 per million input tokens; output is free). `402`, `error_type: "budget_exceeded_error"`. The key's remaining budget is in the `x-proxy-budget-remaining-usd` header. |
| Expiry / disabled | `expires_at` or `"enabled": false` per key. `403`, `error_type: "permission_error"`. |
| Usage log | One JSON line per request (key name, path, status, ms, tokens, cost). Request bodies are never logged. |
| Persistence | Usage counters are saved to `usage.json` every 5 s and on shutdown. |
| CORS | On by default (`CORS_ORIGIN=*`) so browser apps can call it. |
| Body limit | Requests over `MAX_BODY_BYTES` (512 KB) get `413`, `error_type: "request_too_large"`, before anything is sent on. |
| Errors | Proxy errors use TypeSafe's shape: `{ "detail": { "error_type": "...", "message": "..." } }`. A wrong key gets TypeSafe's exact 401 message. Upstream down or timed out = `502`, `error_type: "api_error"`. Every response has an `x-request-id` (the proxy's, for its log); proxy-made errors also set `x-typesafe-request-id` so SDKs show an id. The log stores both ids. |

## Admin

Set `ADMIN_TOKEN`, then:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://your-proxy/admin/usage
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://your-proxy/admin/keys
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" https://your-proxy/admin/keys/reload
```

`GET /health` is public and returns `{ ok, mode, keys }`.

## Deploy

```bash
docker build -t jev-proxy ./proxy
docker run -d -p 8787:8787 -v $PWD/proxy-data:/data \
  -e JEV_API_KEY=apikey_... -e ADMIN_TOKEN=... jev-proxy
```

Put `keys.json` in the mounted `/data` folder. Run behind HTTPS (Caddy, nginx, Fly.io, Render, Cloud Run).
Any host that runs a Docker image or `node src/server.js` works.

## Configuration

See [`.env.example`](.env.example). Every setting is an environment variable.

## Tests

```bash
npm test
```

Tests start a fake upstream and check: key swap, header stripping, balance hiding, rate limit,
daily limit, budget cap (also across restarts), expiry, disabled keys, body limit, upstream timeout,
error pass-through, 529 and retry headers, request ids, CORS, admin endpoints, key reload, the key
generator, that request bodies never reach the log, and the mock against the recorded real-API cases.

Re-record the fixture after an API change: send each `request` in the file to the real API and
update `expect` (keep only `type`, `loc` and `msg` of 422 errors).

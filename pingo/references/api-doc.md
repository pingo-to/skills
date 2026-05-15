# Pingo Public API Reference

This is the canonical reference for Pingo's public REST API
(`/v1/*`). It mirrors the live, copy-paste-ready docs page at
[https://pingo.to/docs](https://pingo.to/docs), trimmed to one
language (curl) and rendered as plain markdown for offline reading.

For a Python wrapper around these endpoints, see this skill's
`scripts/pingo.py` (covered in `SKILL.md`). The script is generally
preferable to writing raw HTTP calls.

## Base URL

```
https://api.pingo.to/v1
```

Override with `PINGO_BASE_URL` only when targeting a non-production
environment (e.g. a local dev cluster).

## Authentication

Every endpoint requires a personal API key, sent as a `Bearer` token:

```
Authorization: Bearer pingo_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Keys are issued from `https://pingo.to/keys` and always begin with the
`pingo_` prefix. Keys cannot be recovered if leaked — revoke and rotate
on suspected compromise.

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/pin/file` | Upload and pin a file (multipart) |
| `POST` | `/v1/pin/json` | Pin a JSON document (stored as `application/json`) |
| `POST` | `/v1/pin/text` | Pin raw text (stored as `text/plain`) |
| `GET` | `/v1/pin/cid/:cid` | Look up one pin by CID |
| `PUT` | `/v1/pin/cid/:cid/name` | Rename a pin (display name only) |
| `DELETE` | `/v1/pin/cid/:cid` | Delete a pin (storage refunded immediately) |
| `GET` | `/v1/pins` | List pins, paginated and searchable |
| `GET` | `/v1/account` | Plan, storage usage, gateway domain |

All response bodies are JSON with snake_case fields. CIDs are returned
in v1 form (`bafy…` / `bafk…`); v0 inputs (`Qm…`) are accepted and
silently normalised on lookup paths.

---

## POST /v1/pin/file

Upload a file via `multipart/form-data` and pin it. The pin completes
synchronously — the `200` response carries a usable `gateway_url`.

### Form fields

- `file` — the file payload (required, single field)

### Allowed file types

The file's **content** (not its extension) is sniffed with
`gabriel-vasile/mimetype`. The accepted set depends on the caller's
plan.

**Paid plans (Pro, Premium)** — any file type is accepted (PDFs,
archives, video, audio, fonts, office documents, binaries, …). The
detected MIME is stored and served as-is, with two carve-outs for
gateway safety:

- **Active web content** — `text/html`, `text/css`, `text/javascript`,
  `application/javascript` — is force-stored as `text/plain` so the
  public gateway cannot host phishing pages or serve third-party
  scripts.
- **SVG** is scanned and rejected if it contains `<script>`, event
  handlers (`on*`), `<foreignObject>`, `<iframe>`, or
  external/javascript URLs (`400 unsafe_svg`).

**Free plan** — a narrower allowlist; anything outside returns
`400 unsupported_mime`:

- **Images** served as their natural MIME: `jpeg`, `png`, `webp`,
  `gif`, `svg`, `ico`. SVG goes through the same scan as on paid
  plans.
- **Text and source code** — any text-based format is accepted and
  **stored as `text/plain`**. Common examples: `txt`, `md`, `html`,
  `css`, `js`, `xml`, `csv`, `log`, plus most programming source
  files (`py`, `go`, `rs`, `rb`, `java`, `sh`, `sql`, `yaml`, `toml`,
  `ini`). The same active-content downgrade applies.
- **JSON** served as `application/json` (preserved, not
  downgraded) so consumers like NFT marketplaces and IPNS readers get
  the Content-Type they expect.

### Request

```sh
curl -X POST https://api.pingo.to/v1/pin/file \
  -H "Authorization: Bearer pingo_..." \
  -F "file=@./path/to/your-file.png"
```

### Response (200)

```json
{
  "cid":         "bafybei...",
  "name":        "your-file.png",
  "size_bytes":  42384,
  "via":         "pin-file",
  "gateway_url": "https://<slug>.<gateway>/ipfs/bafybei...",
  "created_at":  "2026-04-26T..."
}
```

### Error responses

- `400 file_field_required` — multipart form missing the `file` field
- `400 unsupported_mime` — **Free plan only**: sniffed MIME isn't in
  the Free allowlist; response carries `detected` with the actual
  MIME. Paid plans never return this `unsupported_mime` error.
- `400 unsafe_svg` — SVG contains scripts, event handlers, foreign
  objects, iframes, or external/javascript URLs; `detected` is always
  `image/svg+xml`
- `403 cid_blocked` — the resolved CID has been removed by a Pingo
  moderator (DMCA, abuse) and cannot be pinned by anyone
- `409 cid_already_pinned` — same content already pinned to this
  account; the canonical CID is echoed in the `cid` field
- `413 single_file_quota` — file exceeds the per-file cap (Free 10 MB,
  Pro 20 MB, Premium 50 MB); body has `size` and `limit`
- `413 storage_quota` — at storage cap; body has `used` and `limit`
- `429 monthly_pin_quota` — Free plan only; monthly allowance
  exhausted; body has `used`, `limit`, `resets_at`
- `429 rate_limit` — too many requests; body has `retry_after`
  (seconds)
- `503 storage_unavailable` — storage temporarily unavailable; retry
  shortly

---

## POST /v1/pin/json

Pin a JSON document. Useful for NFT metadata, structured feeds, and
any consumer that strict-checks `Content-Type`. The CID is computed
from the canonical content. Pin completes synchronously.

### Request body

```json
{
  "name":    "display name (required, max 100 chars)",
  "content": "any valid JSON value (object, array, string, number, bool, null)"
}
```

### Request

```sh
curl -X POST https://api.pingo.to/v1/pin/json \
  -H "Authorization: Bearer pingo_..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "metadata.json",
    "content": {
      "name":   "NFT #1",
      "author": "John Doe"
    }
  }'
```

### Response (200)

```json
{
  "cid":         "bafkrei...",
  "name":        "metadata.json",
  "size_bytes":  64,
  "mime_type":   "application/json",
  "via":         "pin-json",
  "gateway_url": "https://<slug>.<gateway>/ipfs/bafkrei...",
  "created_at":  "2026-04-26T..."
}
```

### Error responses

- `400 invalid_body` — request body not parseable as JSON, or
  `content` itself isn't valid JSON
- `400 name_required` — empty `name`
- `400 name_too_long` — `name` exceeds 100 characters
- `400 content_required` — `content` field is missing
- `403 cid_blocked` — see `/v1/pin/file`
- `409 cid_already_pinned` — see `/v1/pin/file`
- `413 single_file_quota` / `413 storage_quota` — see `/v1/pin/file`
- `429 monthly_pin_quota` / `429 rate_limit` — see `/v1/pin/file`
- `503 storage_unavailable` — see `/v1/pin/file`

---

## POST /v1/pin/text

Pin raw text. Useful for short payloads (notes, snippets, plain-text
logs). For JSON documents prefer `/v1/pin/json`, which stores the pin
with `Content-Type: application/json`.

### Request body

```json
{
  "name":    "display name (required, max 100 chars)",
  "content": "the literal text to pin"
}
```

### Request

```sh
curl -X POST https://api.pingo.to/v1/pin/text \
  -H "Authorization: Bearer pingo_..." \
  -H "Content-Type: application/json" \
  -d '{
    "name":    "hello.txt",
    "content": "Hello, Pingo!"
  }'
```

### Response (200)

```json
{
  "cid":         "bafkrei...",
  "name":        "hello.txt",
  "size_bytes":  12,
  "via":         "pin-text",
  "gateway_url": "https://<slug>.<gateway>/ipfs/bafkrei...",
  "created_at":  "2026-04-26T..."
}
```

### Error responses

- `400 invalid_body` — body could not be parsed
- `400 name_required` / `400 name_too_long`
- `403 cid_blocked` — see `/v1/pin/file`
- `409 cid_already_pinned` — see `/v1/pin/file`
- `413 single_file_quota` / `413 storage_quota`
- `429 monthly_pin_quota` / `429 rate_limit`
- `503 storage_unavailable`

---

## GET /v1/pin/cid/:cid

Look up a single pin by CID. Both v0 (`Qm…`) and v1 (`bafy…`) forms
are accepted; the API normalises to v1 before lookup.

### Request

```sh
curl -H "Authorization: Bearer pingo_..." \
  https://api.pingo.to/v1/pin/cid/bafybeibwzifw52ttrkqlikfzext5akxu7lz4xiwjgwzmqcpdzmp3n5vnbe
```

### Response (200)

```json
{
  "cid":         "bafybei...",
  "name":        "my-readme",
  "size_bytes":  12345,
  "mime_type":   "text/plain",
  "via":         "pin-file",
  "gateway_url": "https://<slug>.<gateway>/ipfs/bafybei...",
  "created_at":  "2026-04-26T..."
}
```

Conditional fields:

- `mime_type` — content-sniffed MIME for the stored file
  (e.g. `image/png`, `image/svg+xml`); `"text/plain"` for content
  created via `POST /v1/pin/text`. Omitted on pre-existing rows
  created before this field was added.

### Error responses

- `400 invalid_cid` — CID format unrecognised
- `404 Not Found` — no pin for this user with this CID

---

## PUT /v1/pin/cid/:cid/name

Update the display name for a pin. The CID and content are unchanged.
Empty names are rejected; max 100 characters.

### Request body

```json
{ "name": "new display name" }
```

### Request

```sh
curl -X PUT https://api.pingo.to/v1/pin/cid/bafybei.../name \
  -H "Authorization: Bearer pingo_..." \
  -H "Content-Type: application/json" \
  -d '{"name": "renamed.png"}'
```

### Response

`204 No Content` on success.

### Error responses

- `400 invalid_body` — body could not be parsed
- `400 invalid_cid` — CID format unrecognised
- `400 name_required` — empty `name`
- `400 name_too_long` — `name` exceeds 100 characters
- `404 Not Found` — no pin for this user with this CID

---

## DELETE /v1/pin/cid/:cid

Delete a pin. Storage usage is refunded immediately; the pin is gone
from `GET /v1/pins` and `GET /v1/pin/cid/:cid` right away.

### Request

```sh
curl -X DELETE https://api.pingo.to/v1/pin/cid/bafybei... \
  -H "Authorization: Bearer pingo_..."
```

### Response

`204 No Content` on success.

### Error responses

- `400 invalid_cid` — CID format unrecognised
- `404 Not Found` — no matching pin for this user

---

## GET /v1/pins

List your pins, newest first. Supports pagination and an optional
search query.

### Query parameters

- `page` — 1-indexed page number (default `1`)
- `size` — page size, max `100` (default `20`)
- `q` — optional search query. Substring (case-insensitive) match on
  `name`, exact match on the CID (v0 or v1). When `q` is set, `page`
  and `size` are ignored.

### Request

```sh
curl -H "Authorization: Bearer pingo_..." \
  "https://api.pingo.to/v1/pins?page=1&size=20"
```

### Response (200)

```json
{
  "items": [
    { "cid": "bafkrei...", "name": "hello.txt",
      "size_bytes": 12,   "created_at": "..." },
    { "cid": "bafybei...", "name": "logo.png",
      "size_bytes": 4096, "created_at": "..." }
  ],
  "page":      1,
  "page_size": 20,
  "total":     2
}
```

### Error responses

- `429 rate_limit` — too many requests; body has `retry_after`

---

## GET /v1/account

Account basics: gateway domain, plan, storage usage and quota.

### Request

```sh
curl -H "Authorization: Bearer pingo_..." \
  https://api.pingo.to/v1/account
```

### Response (200)

```json
{
  "gateway_domain_slug": "your-slug",
  "gateway_domain":      "your-slug.pingogate.example.com",
  "plan":                "pro",
  "storage_used_size":   12345678,
  "storage_quota_size":  214748364800
}
```

`plan` is one of `"free"`, `"pro"`, `"premium"`. Storage sizes are in
bytes.

---

## Error format

Every error response is a JSON object with a stable, snake_case
`error` field. **Branch on this field, not on the human wording** —
wording may change; codes will not.

The HTTP status tells you the category (4xx client, 5xx server); the
`error` code disambiguates within a category. For example, a `429` can
mean either `monthly_pin_quota` or `rate_limit` — the code tells you
which, and any extra fields carry the context for that case.

### A simple error

```
HTTP/1.1 400 Bad Request

{ "error": "name_required" }
```

### An error with context

```
HTTP/1.1 429 Too Many Requests

{
  "error":       "rate_limit",
  "retry_after": 30
}
```

### Error codes that carry extra fields

| Code | Extra fields |
|---|---|
| `monthly_pin_quota` | `used`, `limit`, `resets_at` |
| `rate_limit` | `retry_after` (seconds) |
| `storage_quota` | `used`, `limit` |
| `single_file_quota` | `size`, `limit` |
| `cid_already_pinned` | `cid` (the existing pin's canonical CID) |
| `unsupported_mime` | `detected` (the MIME we sniffed) |
| `unsafe_svg` | `detected` (always `image/svg+xml`) |

All other codes (`name_required`, `invalid_body`, `invalid_cid`,
`file_field_required`, `content_required`, `name_too_long`,
`cid_blocked`, `storage_unavailable`) are bare: `{ "error": "<code>" }`.

### Retry-able vs not

- **Retry with backoff**: `429 rate_limit` (honour `retry_after`),
  `503 storage_unavailable` (short delay then retry).
- **Don't retry, fix and retry**: anything `4xx` other than
  `rate_limit`. Adjust the request before resending.
- **Don't retry**: `403 cid_blocked` (moderator removal —
  the content is permanently unpinnable for everyone) and
  `409 cid_already_pinned` (the response already gives you the
  existing CID).

---

## Gateway URLs

Every pin response includes a `gateway_url` of the form

```
https://<your-slug>.<gateway-domain>/ipfs/<cid>
```

Pingo's gateway sets the `Content-Type` from the stored `mime_type`
(falling back to the IPFS gateway's own detection for older pins).
HTML/JS/CSS uploads are downgraded to `text/plain` for safety; SVG
and JSON are served with their natural MIME so they render and parse
correctly.

Use `gateway_domain` from `GET /v1/account` to discover the host
suffix if you need to construct gateway URLs from a bare CID.

---
name: pingo
description: Use Pingo (an IPFS pinning service) from a code agent — pin files or text to IPFS, pin a CID that already exists on IPFS (Pro / Premium), look up pinned CIDs, list or search the user's pins, rename, delete, or check account storage and quota. Trigger this skill whenever the user mentions Pingo, asks to pin or upload anything to IPFS, asks to pin an existing CID, asks about a CID they previously pinned, asks about their Pingo account / plan / storage usage, or asks about their gateway URL. Also trigger for natural phrasings like "is X pinned", "show my pins", "upload this to IPFS", "pin this CID", "what's my Pingo usage" — even when they don't explicitly say the word "Pingo".
---

# Pingo CLI Skill

Pingo is an IPFS pinning service. This skill wraps Pingo's public REST
API (`/v1/*`) in a single Python CLI that uses **only the standard
library** — no `pip install` required. Use it to drive pin / lookup /
delete / account operations without writing the HTTP code by hand.

The script lives at `scripts/pingo.py` inside this skill folder. Invoke
it with `python3` and the absolute path. Output defaults to JSON on
stdout (designed for you to parse and then summarise to the user). Pass
`--human` for friendly text rendering when the user clearly wants a
chat-style answer.

## Setup — required before first use

The CLI authenticates with `PINGO_API_KEY` and (optionally)
`PINGO_BASE_URL` (defaults to `https://api.pingo.to/v1`).

**If the script exits with `ERROR: PINGO_API_KEY is not set`**, do this:

1. Stop. Tell the user — do not ask them to paste the key into chat
   (it would land in the conversation transcript). Show them this:

   > To use Pingo I need an API key. Create one at
   > https://pingo.to/keys, then expose it to your shell.
   >
   > **One-shot** (this terminal only):
   > ```sh
   > export PINGO_API_KEY=pingo_xxx
   > ```
   >
   > **Persist it** so you don't have to set it every time. Append the
   > line to the rc file your shell uses:
   > ```sh
   > # zsh (default on macOS)
   > echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.zshrc && source ~/.zshrc
   >
   > # bash on Linux
   > echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.bashrc && source ~/.bashrc
   >
   > # bash on macOS (Terminal opens login shells)
   > echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.bash_profile && source ~/.bash_profile
   >
   > # fish
   > echo 'set -gx PINGO_API_KEY pingo_xxx' >> ~/.config/fish/config.fish
   > ```
   >
   > After that, start a new terminal (or `source` the file you just
   > edited) and the env var will be picked up automatically.

2. Once the user confirms it's set, retry the original command.

Optional override (only needed for development or non-default
environments — most users never set this):
```sh
export PINGO_BASE_URL=https://your-pingo-host/v1
```

If `PINGO_BASE_URL` points at a host with a self-signed TLS cert
(e.g. a local dev setup behind Caddy), Python will refuse to connect
with `CERTIFICATE_VERIFY_FAILED`. Either pass `--insecure` per call
or `export PINGO_INSECURE=1`. Don't suggest this for the default
production endpoint.

## Quick reference

| Subcommand | Purpose |
|---|---|
| `pin-file <path>` | Upload + pin a local file (multipart). |
| `pin-text <name> --content "..."` | Pin a string of text. Or `--from-stdin` to pipe content. |
| `pin-json <name> --content '{...}'` | Pin a JSON document, stored with `Content-Type: application/json`. Or `--from-stdin`. |
| `pin-cid <cid> --name "..."` | Pin a CID that already exists on IPFS (Pro / Premium plans). Returns immediately with `status: queued`; poll `get-pin <cid>` until status reaches `pinned` or `failed`. |
| `get-pin <cid>` | Look up one pin by CID. Returns `{pinned:false, cid}` (not an error) on 404. |
| `list-pins [--q <query>] [--page N] [--size N]` | List or search the user's pins. |
| `rename-pin <cid> <new-name>` | Rename a pin's display name. |
| `delete-pin <cid>` | Delete a pin. Storage quota is refunded immediately. |
| `account` | Show plan, storage usage, quota, gateway domain. |

Add `--human` (before the subcommand) on any call when the user wants
readable output instead of JSON.

## Mapping natural-language asks to commands

The user says it; you run it. Substitute the real absolute path to the
script. Default to JSON output and parse it yourself before answering;
use `--human` only when the user clearly wants the answer rendered as
text (e.g. "show me my usage").

### "Pin this file: ./photo.png"
```sh
python3 <skill-dir>/scripts/pingo.py pin-file ./photo.png
```
Quote the `cid` and `gateway_url` from the response.

### "Pin this text as readme.md: Hello world"
```sh
python3 <skill-dir>/scripts/pingo.py pin-text readme.md --content "Hello world"
```
For longer content, prefer stdin to avoid escaping headaches:
```sh
cat README.md | python3 <skill-dir>/scripts/pingo.py pin-text readme.md --from-stdin
```

### "Pin this JSON as metadata.json: { ... }"
```sh
python3 <skill-dir>/scripts/pingo.py pin-json metadata.json \
  --content '{"name":"NFT #1","author":"John Doe"}'
```
For larger documents, prefer stdin:
```sh
cat metadata.json | python3 <skill-dir>/scripts/pingo.py pin-json metadata.json --from-stdin
```
Use this (not `pin-text`) when the consumer expects a JSON Content-Type
— NFT marketplaces, IPNS records, structured feeds. The script
validates the JSON locally before sending.

### "Pin this CID that's already on IPFS: bafy..." (Pro / Premium only)
```sh
python3 <skill-dir>/scripts/pingo.py pin-cid bafy... --name "remote file"
```
Returns immediately with `status: "queued"`. The pin runs in the
background. Poll with `get-pin` until status reaches `pinned` or
`failed`:
```sh
python3 <skill-dir>/scripts/pingo.py get-pin bafy...
```
A typical run goes `queued` → `pinning` → `pinned` in seconds to
a couple of minutes (depends on how quickly the content can be
located on the IPFS network). On `pinned`, the response includes
`gateway_url`. On `failed`, the response includes a `failure_reason`
string — see "Interpreting errors" below for the codes.

If the user is on the Free plan, this call returns
`403 plan_not_eligible`. Tell them pin-by-CID requires Pro or
Premium and point them at https://pingo.to/account/plan.

### "Did I pin this CID? bafy..."
```sh
python3 <skill-dir>/scripts/pingo.py get-pin bafy...
```
JSON `{"pinned": false, "cid": "..."}` means no. A pin object means yes;
quote `gateway_url` so the user can click through.

### "Show me what I've pinned"
```sh
python3 <skill-dir>/scripts/pingo.py --human list-pins
```
With a search query (substring on name OR exact CID match):
```sh
python3 <skill-dir>/scripts/pingo.py list-pins --q "logo"
```

### "Rename bafy... to my-logo.png"
```sh
python3 <skill-dir>/scripts/pingo.py rename-pin bafy... my-logo.png
```

### "Delete / unpin bafy..."
```sh
python3 <skill-dir>/scripts/pingo.py delete-pin bafy...
```
Storage quota is refunded immediately on the user's account.

### "What's my Pingo usage / plan / quota?"
```sh
python3 <skill-dir>/scripts/pingo.py --human account
```

## Interpreting errors for the user

When a request fails, surface the meaningful part — don't dump raw
JSON unless they asked. The script already prints HTTP status + the
error body to stderr; here's how to translate the common `error` codes
into something useful to say:

| Code | What to tell the user |
|---|---|
| `monthly_pin_quota` | Free plan's monthly pin allowance is exhausted. The body's `resets_at` says when it resets; mention that Pro/Premium have higher caps. |
| `storage_quota` | Hit the storage cap (`used / limit`). Suggest deleting unused pins or upgrading. |
| `single_file_quota` | The file is bigger than the per-file cap (Free 10 MB / Pro 20 MB / Premium 50 MB). The body has `size` and `limit`. |
| `unsupported_mime` | **Free plan only.** File type isn't in the Free allowlist; the `detected` field shows what was sniffed. Free accepts text/source code (stored as `text/plain`) and common images (jpeg/png/webp/gif/svg/ico). Paid plans (Pro/Premium) accept any file type — mention upgrading if the user wants PDFs, archives, video, etc. |
| `unsafe_svg` | SVG contains scripts, event handlers, foreign objects, iframes, or external/javascript URLs. Strip those and retry. |
| `account_suspended` | Rare. The account has been suspended by a Pingo moderator (DMCA, phishing, malware, CSAM, traffic abuse, etc.). New pins are blocked. |
| `cid_already_pinned` | The CID is already pinned to this user's account. The `cid` field echoes it; offer to look it up, rename, or delete instead. |
| `plan_not_eligible` | Pin-by-CID requires a Pro or Premium plan. Suggest upgrading at https://pingo.to/account/plan. |
| `pin_cid_queue_full` | Too many pin-by-CID requests already in flight on this account. Suggest waiting for the existing ones to finish and retrying. |
| `rate_limit` | Too many requests. The body's `retry_after` (seconds) tells when it's safe to try again. |
| `invalid_cid` | The CID couldn't be parsed (must be valid v0 `Qm…` or v1 `bafy…`). |
| `name_required` / `name_too_long` | Ask for a non-empty name ≤ 100 chars. |
| `content_required` | `pin-json` was called without a JSON body. Pass `--content '{...}'` or pipe via `--from-stdin`. |
| `invalid_body` | The request body wasn't parseable JSON. For `pin-json` the script catches this client-side, so this only surfaces if the user routed around it; show the raw error. |

## Pin-by-CID: interpreting `failure_reason`

When `get-pin` returns a row with `status: "failed"` (always a
pin-by-CID row — synchronous uploads never reach this state), the
response carries a `failure_reason` string. Branch on the code:

| `failure_reason` | What to tell the user |
|---|---|
| `cid_blocked` | This CID is on Pingo's moderation blocklist and cannot be pinned by anyone. |
| `cid_unreachable` | Pingo couldn't locate this CID on the IPFS network. Confirm the CID is correct and that at least one provider has it online, then retry. |
| `cid_is_directory` | Pin-by-CID supports files only, not directories. |
| `single_file_quota` | Content exceeds the per-file cap (Pro 20 MB / Premium 50 MB). |
| `storage_quota` | Pinning the content would push usage past the storage cap. Suggest deleting unused pins or upgrading. |
| `fetch_timeout` | Timed out while fetching the content from IPFS. Suggest retrying later. |
| `pin_failed` | IPFS rejected the pin. Suggest retrying later. |
| `unsafe_svg` | SVG carries scripts, event handlers, or external / javascript URLs. Strip them and re-pin. |

To retry a failed pin, just call `pin-cid` again with the same CID
— the previous failed row is replaced automatically. If the user
wants to clear a failed row without retrying (e.g. they gave up on
that CID), `delete-pin <cid>` removes it.

## Notes for the agent

- `pin-file` reads the whole file into memory as one multipart request.
  For files near the per-plan max (10–50 MB) this is fine on any
  modern machine; don't try it for multi-GB files (which the API
  rejects anyway).
- `pin-text` accepts either `--content "..."` or `--from-stdin`. Use
  stdin for content with shell-meta characters or newlines — much
  cleaner than escaping.
- `get-pin` deliberately translates HTTP 404 into
  `{"pinned": false, "cid": "..."}` (exit 0) so a "did I pin this?"
  check is a single call without try/except.
- The API always returns v1 CIDs (`bafy…`) in responses. v0 input
  (`Qm…`) is normalised silently, so don't worry about conversion on
  the user's behalf — pass whatever the user gave you.
- This skill covers Pingo's public API. Operations only available
  from the Pingo dashboard UI (signup, billing, plan changes,
  account management) aren't covered here — point the user at
  https://pingo.to for those.
- For raw HTTP details (paths, request shapes, response schemas,
  full error code list) consult
  [`references/api-doc.md`](references/api-doc.md). The CLI in
  `scripts/pingo.py` is the preferred way to call the API — only
  drop down to raw HTTP when the user explicitly asks for it or
  when the CLI doesn't cover the operation.

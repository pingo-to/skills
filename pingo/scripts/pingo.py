#!/usr/bin/env python3
"""Pingo CLI — call the Pingo public API from the command line.

Stdlib-only. No `pip install` required. Used by the Pingo Claude Code
skill, but works as a regular CLI too.

Auth:    PINGO_API_KEY    (required)
Endpoint: PINGO_BASE_URL  (optional; default https://api.pingo.to/v1)

Output:
  - Default: pretty-printed JSON on stdout. Designed for an LLM agent
    to parse and then summarise to the user.
  - With --human: friendly text rendering, no JSON.
  - Errors: HTTP status + the JSON error body on stderr, exit != 0.

Pingo's error codes are stable snake_case strings (monthly_pin_quota,
storage_quota, single_file_quota, unsupported_mime, unsafe_svg,
cid_already_pinned, rate_limit, ...) and may carry extra structured
fields (used, limit, retry_after, detected, cid). Branch on the code,
not the wording.
"""

import argparse
import json
import mimetypes
import os
import ssl
import sys
import uuid
from urllib import error, parse, request

DEFAULT_BASE_URL = "https://api.pingo.to/v1"


# ----- env / config -----------------------------------------------------------


def get_api_key() -> str:
    key = os.environ.get("PINGO_API_KEY", "").strip()
    if not key:
        sys.stderr.write(
            "ERROR: PINGO_API_KEY is not set.\n"
            "Create an API key at https://pingo.to/keys, then expose it\n"
            "to your shell. One-shot:\n"
            "  export PINGO_API_KEY=pingo_xxx\n"
            "Persist it (zsh):\n"
            "  echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.zshrc && source ~/.zshrc\n"
            "Or for bash, append to ~/.bashrc (or ~/.bash_profile on macOS).\n"
        )
        sys.exit(2)
    return key


def get_base_url() -> str:
    return os.environ.get("PINGO_BASE_URL", "").strip() or DEFAULT_BASE_URL


# Module-level so call() can read it. Set by main() from --insecure
# or the PINGO_INSECURE env var. Only intended for local development
# against a self-signed cert (e.g. Caddy's local CA).
_INSECURE = False


def _ssl_context():
    if not _INSECURE:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ----- HTTP -------------------------------------------------------------------


def call(
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    content_type: str | None = None,
):
    """Make an authenticated request. Returns (status, body_obj).

    body_obj is the parsed JSON if the response body looks like JSON,
    otherwise the raw bytes, otherwise None.
    """
    url = get_base_url().rstrip("/") + path
    headers = {"Authorization": f"Bearer {get_api_key()}"}
    if content_type:
        headers["Content-Type"] = content_type
    req = request.Request(url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, context=_ssl_context()) as resp:
            return resp.status, _try_json(resp.read())
    except error.HTTPError as e:
        # 4xx/5xx still carry useful body — read it before propagating.
        return e.code, _try_json(e.read())


def _try_json(body: bytes):
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body


def encode_multipart(
    fields: dict, files: list
) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Stdlib doesn't ship a multipart
    encoder so this is hand-rolled; it's small enough to be obvious.

    files: list of (name, filename, content_bytes, content_type) tuples.
    """
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        parts.append(value.encode("utf-8") if isinstance(value, str) else value)
        parts.append(b"\r\n")
    for name, filename, content, ctype in files:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'
            ).encode()
        )
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# ----- formatting helpers -----------------------------------------------------


def human_bytes(n) -> str:
    if not n:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    if i == 0:
        return f"{int(v)} {units[i]}"
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{s} {units[i]}"


def emit_json(obj):
    print(json.dumps(obj, indent=2))


def fail(status: int, body):
    """Print HTTP status + body to stderr and exit non-zero. Always
    emits JSON for the body when possible so the agent can parse the
    error code field."""
    sys.stderr.write(f"HTTP {status}\n")
    if isinstance(body, dict):
        sys.stderr.write(json.dumps(body, indent=2) + "\n")
    elif isinstance(body, bytes):
        sys.stderr.write(body.decode("utf-8", errors="replace") + "\n")
    sys.exit(1)


def emit_pin(status, body, human: bool):
    if status not in (200, 201):
        fail(status, body)
    if human:
        print(f"Pinned: {body.get('cid')}")
        if body.get("gateway_url"):
            print(f"URL:    {body['gateway_url']}")
        if body.get("name"):
            print(f"Name:   {body['name']}")
        sz = body.get("size_bytes")
        if sz is not None:
            print(f"Size:   {human_bytes(sz)}")
        if body.get("mime_type"):
            print(f"MIME:   {body['mime_type']}")
    else:
        emit_json(body)


# ----- subcommands ------------------------------------------------------------


def cmd_pin_file(args):
    if not os.path.isfile(args.path):
        sys.stderr.write(f"ERROR: file not found: {args.path}\n")
        sys.exit(2)
    with open(args.path, "rb") as f:
        content = f.read()
    filename = os.path.basename(args.path)
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body, ct = encode_multipart({}, [("file", filename, content, ctype)])
    status, resp = call("POST", "/pin/file", data=body, content_type=ct)
    emit_pin(status, resp, args.human)


def cmd_pin_text(args):
    if args.content is None and not args.from_stdin:
        sys.stderr.write("ERROR: provide --content '...' or --from-stdin\n")
        sys.exit(2)
    text = args.content if args.content is not None else sys.stdin.read()
    payload = json.dumps({"name": args.name, "content": text}).encode("utf-8")
    status, resp = call(
        "POST", "/pin/text", data=payload, content_type="application/json"
    )
    emit_pin(status, resp, args.human)


def cmd_pin_json(args):
    if args.content is None and not args.from_stdin:
        sys.stderr.write("ERROR: provide --content '...' or --from-stdin\n")
        sys.exit(2)
    raw = args.content if args.content is not None else sys.stdin.read()
    # Validate JSON locally so the user gets a precise parse error
    # (line/column) rather than a generic 400 invalid_body from the API.
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"ERROR: invalid JSON: {e}\n")
        sys.exit(2)
    payload = json.dumps({"name": args.name, "content": parsed}).encode("utf-8")
    status, resp = call(
        "POST", "/pin/json", data=payload, content_type="application/json"
    )
    emit_pin(status, resp, args.human)


def cmd_get_pin(args):
    status, resp = call("GET", f"/pin/cid/{parse.quote(args.cid)}")
    if status == 404:
        # "Did I pin this CID?" is a common ask. Make a not-found
        # answer easy to consume rather than an error to catch.
        if args.human:
            print(f"Not pinned: {args.cid}")
        else:
            emit_json({"pinned": False, "cid": args.cid})
        return
    emit_pin(status, resp, args.human)


def cmd_list_pins(args):
    params = {}
    if args.q:
        params["q"] = args.q
    if args.page:
        params["page"] = str(args.page)
    if args.size:
        params["size"] = str(args.size)
    qs = ("?" + parse.urlencode(params)) if params else ""
    status, resp = call("GET", "/pins" + qs)
    if status != 200:
        fail(status, resp)
    if args.human:
        items = resp.get("items", [])
        if not items:
            print("No pins.")
            return
        total = resp.get("total", len(items))
        print(f"{total} pin(s):")
        for it in items:
            print(
                f"  {it.get('cid', '?')}  "
                f"{human_bytes(it.get('size_bytes', 0))}  "
                f"{it.get('name', '')}"
            )
    else:
        emit_json(resp)


def cmd_rename_pin(args):
    payload = json.dumps({"name": args.name}).encode("utf-8")
    status, resp = call(
        "PUT",
        f"/pin/cid/{parse.quote(args.cid)}/name",
        data=payload,
        content_type="application/json",
    )
    if status == 204:
        if args.human:
            print(f"Renamed {args.cid} → {args.name}")
        else:
            emit_json({"ok": True, "cid": args.cid, "name": args.name})
        return
    fail(status, resp)


def cmd_delete_pin(args):
    status, resp = call("DELETE", f"/pin/cid/{parse.quote(args.cid)}")
    if status == 204:
        if args.human:
            print(f"Deleted {args.cid}")
        else:
            emit_json({"ok": True, "cid": args.cid})
        return
    fail(status, resp)


def cmd_account(args):
    status, resp = call("GET", "/account")
    if status != 200:
        fail(status, resp)
    if args.human:
        used = resp.get("storage_used_size", 0)
        quota = resp.get("storage_quota_size", 0)
        plan = resp.get("plan", "?")
        slug = resp.get("gateway_domain_slug", "?")
        gateway = resp.get("gateway_domain", "?")
        pct = (used / quota * 100) if quota else 0
        print(f"Plan:    {plan}")
        print(f"Gateway: {gateway} (slug: {slug})")
        print(f"Storage: {human_bytes(used)} / {human_bytes(quota)} ({pct:.1f}%)")
    else:
        emit_json(resp)


# ----- argparse setup ---------------------------------------------------------


def main():
    p = argparse.ArgumentParser(
        prog="pingo",
        description="Pingo public API client (uses /v1/* with API-key auth).",
    )
    p.add_argument(
        "--human",
        action="store_true",
        help="Friendly text output. Default is JSON for agent parsing.",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help=(
            "Skip TLS certificate verification. Only for local dev "
            "against self-signed certs (e.g. Caddy). Can also be enabled "
            "by setting PINGO_INSECURE=1."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("pin-file", help="Upload + pin a file (multipart).")
    sp.add_argument("path", help="Path to a local file.")
    sp.set_defaults(func=cmd_pin_file)

    sp = sub.add_parser("pin-text", help="Pin a string of text content.")
    sp.add_argument("name", help="Display name for the pin (max 100 chars).")
    sp.add_argument("--content", help="Inline text content.")
    sp.add_argument(
        "--from-stdin",
        action="store_true",
        help="Read text content from stdin instead of --content.",
    )
    sp.set_defaults(func=cmd_pin_text)

    sp = sub.add_parser(
        "pin-json",
        help=(
            "Pin a JSON document. Stored with Content-Type "
            "application/json (good for NFT metadata, IPNS records, etc.)."
        ),
    )
    sp.add_argument("name", help="Display name for the pin (max 100 chars).")
    sp.add_argument(
        "--content",
        help="Inline JSON text (parsed and validated client-side).",
    )
    sp.add_argument(
        "--from-stdin",
        action="store_true",
        help="Read JSON text from stdin instead of --content.",
    )
    sp.set_defaults(func=cmd_pin_json)

    sp = sub.add_parser(
        "get-pin",
        help="Look up one pin by CID. Returns {pinned:false} on 404.",
    )
    sp.add_argument("cid", help="CID (v0 or v1; v0 is normalised to v1).")
    sp.set_defaults(func=cmd_get_pin)

    sp = sub.add_parser("list-pins", help="List or search the user's pins.")
    sp.add_argument("--q", help="Search: name substring (case-insensitive) or exact CID.")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--size", type=int, default=20, help="Page size (max 100).")
    sp.set_defaults(func=cmd_list_pins)

    sp = sub.add_parser("rename-pin", help="Rename a pin by CID.")
    sp.add_argument("cid")
    sp.add_argument("name", help="New display name.")
    sp.set_defaults(func=cmd_rename_pin)

    sp = sub.add_parser("delete-pin", help="Delete a pin by CID.")
    sp.add_argument("cid")
    sp.set_defaults(func=cmd_delete_pin)

    sp = sub.add_parser(
        "account",
        help="Show plan, storage usage, quota, gateway domain.",
    )
    sp.set_defaults(func=cmd_account)

    args = p.parse_args()
    global _INSECURE
    _INSECURE = args.insecure or os.environ.get("PINGO_INSECURE", "") in ("1", "true", "yes")
    args.func(args)


if __name__ == "__main__":
    main()

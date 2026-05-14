# Pingo.to AI skills

AI skills for Pingo ([https://pingo.to](https://pingo.to)), an IPFS pinning service. This
repo packages Pingo's public API into a Claude Code / Codex / Cursor **skill** you can
invoke with `/pingo ...` — pin files, look up CIDs, manage your pins,
or check your account, all without leaving the terminal.

The skill ships a single-file Python CLI ([`pingo/scripts/pingo.py`](pingo/scripts/pingo.py))
that uses only the standard library — no `pip install` required.

## Install

Claude Code:
```bash
npx skills add pingo-to/skills -a claude-code
```

Codex:
```bash
npx skills add pingo-to/skills -a codex
```

Cursor:
```bash
npx skills add pingo-to/skills -a cursor
```

This registers the skill with Claude Code so `/pingo` becomes available
inside any conversation.


## Setup — API key

Pingo authenticates with an API key. Create one at
[pingo.to/keys](https://pingo.to/keys), then expose it to your shell.

**One-shot** (current terminal only):

```sh
export PINGO_API_KEY=pingo_xxx
```

**Persist it** so every new shell picks it up automatically:

```sh
# zsh (default on macOS)
echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.zshrc && source ~/.zshrc

# bash on Linux
echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.bashrc && source ~/.bashrc

# bash on macOS (Terminal opens login shells)
echo 'export PINGO_API_KEY=pingo_xxx' >> ~/.bash_profile && source ~/.bash_profile

# fish
echo 'set -gx PINGO_API_KEY pingo_xxx' >> ~/.config/fish/config.fish
```

After that, start a new terminal (or `source` the rc file you just
edited) and you're ready to go.


## What you can do

Once installed, ask Claude things like:

- **Pin** — "pin this file ./hello.txt", "upload my logo.png to IPFS",
  "pin this JSON as metadata.json"
- **Look up** — "did I pin bafy…?", "is this CID on my account?"
- **List & search** — "show my pins", "find pins with 'logo' in the name"
- **Manage** — "rename bafy… to my-logo.png", "unpin bafy…"
- **Account** — "what's my Pingo usage", "how much storage do I have left",
  "what's my gateway URL"

The skill triggers on natural phrasings too — you don't have to say
"Pingo" explicitly. "Upload this to IPFS" or "show me what I've pinned"
both work.


## Examples

```
$ claude
> /pingo what can I do with this skill?
...
> /pingo pin this file ./hello.txt
✓ Pinned hello.txt
  CID:     bafybeicd…
  Gateway: https://yourslug.pingogate.com/ipfs/bafybeicd…
```

A few more examples:

```
> /pingo pin this JSON as metadata.json: {"name":"NFT #1","author":"Bob"}
> /pingo did I pin bafybeicd…?
> /pingo show me my pins
> /pingo find pins with "logo" in the name
> /pingo rename bafybeicd… to my-logo.png
> /pingo unpin bafybeicd…
> /pingo what's my Pingo plan and usage?
```

## Command reference

Under the hood the skill calls `pingo/scripts/pingo.py`. You can also
invoke it directly if you want shell-level access:

| Subcommand | Purpose |
|---|---|
| `pin-file <path>` | Upload + pin a local file (multipart). |
| `pin-text <name> --content "..."` | Pin a string of text. Use `--from-stdin` to pipe content. |
| `pin-json <name> --content '{...}'` | Pin a JSON document with `Content-Type: application/json`. |
| `get-pin <cid>` | Look up one pin by CID. Returns `{pinned:false}` (not an error) on 404. |
| `list-pins [--q <query>] [--page N] [--size N]` | List or search your pins. |
| `rename-pin <cid> <new-name>` | Rename a pin's display name. |
| `delete-pin <cid>` | Delete a pin. Storage quota is refunded immediately. |
| `account` | Show plan, storage usage, quota, gateway domain. |

Add `--human` before the subcommand for friendly text output (the
default is JSON, optimised for the agent to parse).

```sh
python3 pingo/scripts/pingo.py --human account
python3 pingo/scripts/pingo.py pin-file ./photo.png
cat README.md | python3 pingo/scripts/pingo.py pin-text readme.md --from-stdin
```


## Links

- Skill definition: [`pingo/SKILL.md`](pingo/SKILL.md)
- CLI source: [`pingo/scripts/pingo.py`](pingo/scripts/pingo.py)
- HTTP API reference: [`pingo/references/api-doc.md`](pingo/references/api-doc.md)
- Dashboard & sign-up: [pingo.to](https://pingo.to)
- API key management: [pingo.to/keys](https://pingo.to/keys)

---
name: feishu-streaming-card
description: "Use when deploying, re-applying, or rolling back the Hermes Agent Feishu streaming-card patch (Leorand-dev/hermes-feishu-streaming-card). Triggers: 'apply the streaming card patch', 'redeploy after hermes update', 'rollback the feishu adapter patch', 'verify the feishu card is still streaming', 'solve the feishu truncation problem', 'send long content as a card instead of text', 'bind lark-cli to an existing hermes app'."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, lark, hermes, patch, deploy, rollback, truncation]
    related_skills: [hermes-agent, hermes-gateway-ops]
---

# Feishu Streaming Card

## Overview

The official Hermes Agent Feishu adapter sends text/post messages. Two problems emerge:

1. No typewriter effect. Each edit replaces the whole message (O(N2) rebuild, visual flicker).
2. Truncation. Feishu silently truncates long text messages with certain unicode characters. The user sees block characters (U+2589) where the tail was cut.

Two solutions:

- **A) Adapter patch** applies a git patch to the Feishu adapter. Every response becomes a growing interactive card. O(N2) to O(N).
- **B) Standalone script** (`scripts/stream-card.py`) calls lark-cli API to send/update cards directly. No adapter modification needed.

## When to Use

- Cards stopped appearing after `hermes update`
- Roll back to stock adapter
- "This long message got truncated to a block character" on Feishu
- "Send content as a Feishu card instead of text"
- Bind lark-cli to existing Hermes app

## Files

```
~/.hermes/skills/devops/feishu-streaming-card/
├── SKILL.md
├── references/
│   └── lark-cli-setup.md              # lark-cli binding in Hermes context
└── scripts/
    ├── stream-card.py                  # standalone card sender via lark-cli
    ├── deploy.sh                       # PLANNED: apply/rollback/verify
    ├── restart-gateway.sh              # PLANNED: independent restart
    └── status.sh                       # PLANNED: patch-state check
```

## Solution A: Adapter Patch

### Quick Reference

| Task | Command |
|---|---|
| Apply patch | `cd ~/.hermes/hermes-agent && git apply /tmp/hermes-feishu-streaming-card/feishu-streaming-card.patch` |
| Roll back | `cp adapter.py.bak.\* adapter.py` |
| Check applied | `grep -c '_stream_card_parts' plugins/platforms/feishu/adapter.py` |
| Restart gateway | `setsid nohup python3 /tmp/hermes-feishu-streaming-card/restart-gateway.py > /tmp/restart.log 2>&1 < /dev/null &` |

### Deploy Procedure

1. Clone patch: `git clone --depth 1 https://github.com/Leorand-dev/hermes-feishu-streaming-card /tmp/hermes-feishu-streaming-card`
2. Find adapter: `find ~/.hermes -path "\*feishu\*adapter.py" -not -path "\*.bak\*"`
3. Backup: `cp adapter.py adapter.py.bak.$(date +%s)`
4. Test: `cd ~/.hermes/hermes-agent && git apply --check /tmp/hermes-feishu-streaming-card/feishu-streaming-card.patch`
5. Apply: `git apply /tmp/hermes-feishu-streaming-card/feishu-streaming-card.patch`
6. Syntax check: `python3 -c "import ast; ast.parse(open(adapter_path).read()); print('OK')"`
7. Restart gateway (see Pitfalls -- cannot restart from inside)
8. Verify: send a multi-sentence message -> one growing card, not multiple bubbles

### Rollback

```
LATEST_BAK=$(ls -t ~/.hermes/hermes-agent/plugins/platforms/feishu/adapter.py.bak.* | head -1)
cp "$LATEST_BAK" ~/.hermes/hermes-agent/plugins/platforms/feishu/adapter.py
```
Then restart gateway.

## Solution B: Standalone Script (stream-card.py)

### When to Use

- Push content as a card without modifying the adapter
- Text is getting truncated (block chars)
- lark-cli is installed and bound to the app

### Prerequisites

`lark-cli config bind --source hermes --identity bot-only` must succeed.
Do NOT run `lark-cli config init --new` in Hermes context -- it refuses.

### Usage

```
# Send initial card
stream-card.py init --chat-id oc_xxx "first paragraph"

# Append new content (incremental, not cumulative)
stream-card.py append --state ~/.hermes/stream-card/default.json "next paragraph"

# Finalize (changes header, cleans up state file)
stream-card.py done --state ~/.hermes/stream-card/default.json

# Pipe mode: auto-init on first call, append on subsequent
echo "hello" | stream-card.py pipe --chat-id oc_xxx
```

### State management

State files are JSON in `~/.hermes/stream-card/<name>.json`. Fields:
`message_id`, `chat_id`, `sent_chars` (cursor for cumulative mode),
`elements` (array of card element dicts).

State file is deleted on `done`. Crash mid-stream leaves the file;
next `append` picks up where it left off.

### How it works

1. `init`: POST /open-apis/im/v1/messages with msg_type=interactive, one markdown element
2. `append`: reads state, appends a new markdown element, PATCH /open-apis/im/v1/messages/:id
3. `done`: final PATCH with done header, deletes state file

All calls go through `lark-cli api` (token management, retry, identity scoping).
Does NOT touch the Hermes adapter.

### Solving truncation

Long text messages in Feishu get silently truncated to block characters (U+2589)
when they exceed an internal threshold or contain problematic unicode. Interactive
cards do NOT have this limitation.

Workflow: instead of typing a long text reply that gets truncated, push the
long content into a streaming card via stream-card.py and send a short text
like "see card". The card renders fully.

## Common Pitfalls

1. **Cannot restart gateway from inside.** `hermes gateway restart` is blocked.
   Use setsid + nohup or restart-gateway.py from the patch repo.

2. **git apply --check vs real apply mismatch.** Test with --check first.
   Never use --reject or -3way.

3. **Forgetting to back up.** Without adapter.py.bak.\*, Hermes update destroys
   the clean restore path.

4. **Patch overwritten on hermes update.** Re-apply after every upgrade.

5. **lark-cli config init fails in Hermes context.** Use `config bind --source
   hermes --identity bot-only` instead.

6. **stream-card.py append expects INCREMENTAL content by default.** Pass
   --cumulative only when sending full accumulated text (like the adapter does).

7. **Card element count grows without bound.** Feishu limits cards to ~200
   elements / ~30KB. Manual consolidation may be needed for very long content.

8. **stream-card.py uses lark-cli subprocess.** Each call spawns a node process.
   Do NOT use in a tight loop -- it is for manual/one-shot use, not high-frequency
   streaming (which the adapter patch handles in-process).

## Verification Checklist

- [ ] Patch applied: `grep -c '_stream_card_parts' <adapter.py>` returns > 0
- [ ] Syntax check passes
- [ ] Backup exists
- [ ] 3+ sentence message produces one interactive card, not multiple bubbles
- [ ] stream-card.py executable: `./scripts/stream-card.py --help`
- [ ] lark-cli bound: `lark-cli auth status` shows bot identity "ready"

## One-Shot Recipes

### Re-apply after Hermes update

```bash
cd ~/.hermes/hermes-agent && git apply /tmp/hermes-feishu-streaming-card/feishu-streaming-card.patch && python3 -c "import ast; ast.parse(open('plugins/platforms/feishu/adapter.py').read())"
```

### Push a single card (no patch needed)

```bash
echo "Hello" | ~/.hermes/skills/devops/feishu-streaming-card/scripts/stream-card.py pipe --chat-id oc_xxx
```

### Fix truncated message mid-conversation

```bash
cat <<'EOF' | ~/.hermes/skills/devops/feishu-streaming-card/scripts/stream-card.py pipe --chat-id oc_xxx
<full long content here>
EOF
```
Then tell user "see card".

#!/usr/bin/env python3
"""
Feishu streaming card via lark-cli.
Pure API approach, no Hermes adapter dependency.

Usage:
  ./stream-card.py init --chat-id oc_xxx "hello world"
  ./stream-card.py append --state /tmp/state.json "next paragraph"
  ./stream-card.py done --state /tmp/state.json
"""

import json, os, subprocess, sys, tempfile, textwrap

STATE_DIR = os.path.expanduser("~/.hermes/stream-card")
HEADER = {"title": {"tag": "plain_text", "content": "Hermes"}, "template": "blue"}
CONFIG = {"wide_screen_mode": True}


def run_lark(method, path, data=None, params=None):
    cmd = ["lark-cli", "api", method, path, "--as", "bot", "--format", "json"]
    if params:
        cmd.extend(["--params", json.dumps(params)])
    if data:
        cmd.extend(["--data", json.dumps(data) if isinstance(data, dict) else data])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"lark-cli error: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout)


def build_card(elements, finalize=False):
    status = "done" if finalize else "streaming"
    h = dict(HEADER)
    if status == "done":
        h["title"]["content"] = "Hermes"
    return {
        "config": CONFIG,
        "header": h,
        "elements": elements,
    }


def cmd_init(chat_id, content, state_path):
    formatted = content
    elements = [{"tag": "markdown", "content": formatted}]
    card = build_card(elements)
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    result = run_lark("POST", "/open-apis/im/v1/messages",
                      params={"receive_id_type": "chat_id"},
                      data=payload)
    msg_id = result["data"]["message_id"]
    state = {
        "message_id": msg_id,
        "chat_id": chat_id,
        "sent_chars": len(content),
        "elements": elements,
    }
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, ensure_ascii=False)
    print(f"init ok: {msg_id}")


def cmd_append(content, state_path, finalize=False, cumulative=False):
    with open(state_path) as f:
        state = json.load(f)
    if cumulative:
        sent_chars = state["sent_chars"]
        delta = content[sent_chars:] if len(content) > sent_chars else ""
        if not delta:
            print("no new content to append", file=sys.stderr)
            return
        state["elements"].append({"tag": "markdown", "content": delta})
        state["sent_chars"] = len(content)
    else:
        state["elements"].append({"tag": "markdown", "content": content})
        state["sent_chars"] += len(content)
    card = build_card(state["elements"], finalize=finalize)
    payload = {
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    run_lark("PATCH", f"/open-apis/im/v1/messages/{state['message_id']}", data=payload)
    if finalize:
        os.remove(state_path)
        print(f"done, msg_id={state['message_id']}")
    else:
        with open(state_path, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        print(f"append ok, elements={len(state['elements'])}")


def cmd_done(state_path):
    with open(state_path) as f:
        state = json.load(f)
    card = build_card(state["elements"], finalize=True)
    payload = {
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    run_lark("PATCH", f"/open-apis/im/v1/messages/{state['message_id']}", data=payload)
    os.remove(state_path)
    print(f"done, msg_id={state['message_id']}")


def cmd_pipe(chat_id, state_path):
    content = sys.stdin.read()
    if not content.strip():
        print("empty stdin, nothing to send", file=sys.stderr)
        sys.exit(1)
    if os.path.exists(state_path):
        cmd_append(content, state_path)
    else:
        cmd_init(chat_id, content, state_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "init":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--chat-id", required=True)
        p.add_argument("--state", default=os.path.join(STATE_DIR, "default.json"))
        p.add_argument("content", nargs="*")
        args = p.parse_args(sys.argv[2:])
        content = " ".join(args.content) if args.content else sys.stdin.read()
        cmd_init(args.chat_id, content, args.state)
    elif cmd == "append":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--state", required=True)
        p.add_argument("content", nargs="*")
        args = p.parse_args(sys.argv[2:])
        content = " ".join(args.content) if args.content else sys.stdin.read()
        cmd_append(content, args.state)
    elif cmd == "done":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--state", required=True)
        args = p.parse_args(sys.argv[2:])
        cmd_done(args.state)
    elif cmd == "pipe":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--chat-id", required=True)
        p.add_argument("--state", default=os.path.join(STATE_DIR, "default.json"))
        args = p.parse_args(sys.argv[2:])
        cmd_pipe(args.chat_id, args.state)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

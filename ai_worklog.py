#!/usr/bin/env python3
"""
Codex AI worklog sender for Telegram forum topics.

This script stores a compact local JSONL record and can send the same record to
one Telegram topic per project. It intentionally avoids printing or storing bot
secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import pathlib
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any


STATE_DIR = pathlib.Path.home() / ".local" / "state" / "codex-ai-worklog"
LOG_FILE = STATE_DIR / "ai_worklog.log"
WORKLOG_FILE = STATE_DIR / "worklog.jsonl"
TOPIC_MAP_FILE = STATE_DIR / "topics.json"
DOTENV_NAME = "." + "env"

BOT_TOKEN_KEYS = [
    "AI_WORKLOG_BOT_TOKEN",
    "TELEGRAM_WORKLOG_BOT_TOKEN",
    "TELEGRAM_LLM_NOTI_BOT_TOKEN",
    "LLM_NOTI_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN",
]

WORKLOG_CHAT_ID_KEYS = [
    "AI_WORKLOG_CHAT_ID",
    "TELEGRAM_WORKLOG_CHAT_ID",
    "WORKLOG_CHAT_ID",
    "TELEGRAM_GROUP_CHAT_ID",
]

WORKLOG_TOPIC_ID_KEYS = [
    "AI_WORKLOG_TOPIC_ID",
    "AI_WORKLOG_MESSAGE_THREAD_ID",
    "TELEGRAM_WORKLOG_TOPIC_ID",
    "TELEGRAM_WORKLOG_MESSAGE_THREAD_ID",
]

SECRET_PATTERNS = [
    (
        re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
        "<redacted:telegram-bot-token>",
    ),
    (
        re.compile(
            r"(?i)\b(token|secret|password|passwd|api[_-]?key)\s*=\s*([^\s,;]+)"
        ),
        lambda match: f"{match.group(1)}=<redacted>",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send compact AI turn summaries to a Telegram forum topic."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--send-turn",
        action="store_true",
        help="append/send one AI worklog turn summary",
    )
    mode.add_argument(
        "--print-updates",
        action="store_true",
        help="print sanitized Telegram getUpdates chat/topic ids for setup",
    )
    mode.add_argument(
        "--ensure-topic",
        action="store_true",
        help="create or find the configured project topic and print its id",
    )
    parser.add_argument("--project", help="project key; default is git root basename")
    parser.add_argument("--topic-name", help="Telegram topic name; default is project")
    parser.add_argument("--topic-id", help="message_thread_id to use instead of topic map")
    parser.add_argument("--session-id", help="session id; default is CODEX_THREAD_ID")
    parser.add_argument("--nonce", help="per-turn nonce; generated when omitted")
    parser.add_argument("--user-summary", help="compact summary of the user's request")
    parser.add_argument("--answer-summary", help="compact summary of the answer/result")
    parser.add_argument("--changes", help="files/actions changed by the AI, compact")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and store/print payload without sending Telegram message",
    )
    parser.add_argument(
        "--no-local-log",
        action="store_true",
        help="do not append the local JSONL worklog record",
    )
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config()

    if args.print_updates:
        return print_updates(config)

    project_ctx = project_context(args.project)
    topic_name = sanitize_topic_name(args.topic_name or project_ctx["project"])
    topic_id = args.topic_id or first_value(config, WORKLOG_TOPIC_ID_KEYS)

    if args.ensure_topic:
        token = first_value(config, BOT_TOKEN_KEYS)
        chat_id = first_value(config, WORKLOG_CHAT_ID_KEYS)
        if not token or not chat_id:
            print(
                "Missing AI_WORKLOG_BOT_TOKEN/AI_WORKLOG_CHAT_ID in private config.",
                file=sys.stderr,
            )
            return 1
        ensured = ensure_topic(token, chat_id, topic_name, project_ctx, config)
        print(json.dumps(ensured, ensure_ascii=False, indent=2))
        return 0

    if not args.send_turn:
        parser.print_help()
        return 0

    record = build_record(args, project_ctx, topic_name, topic_id)

    if args.dry_run:
        record["dry_run"] = True
        if not args.no_local_log:
            append_worklog(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if is_disabled(config):
        record["telegram_send_ok"] = None
        record["telegram_status"] = "disabled"
        if not args.no_local_log:
            append_worklog(record)
        log("ai worklog is disabled by AI_WORKLOG_ENABLED")
        return 0

    token = first_value(config, BOT_TOKEN_KEYS)
    chat_id = first_value(config, WORKLOG_CHAT_ID_KEYS)
    if not token or not chat_id:
        record["telegram_send_ok"] = None
        record["telegram_status"] = "not_configured"
        if not args.no_local_log:
            append_worklog(record)
        log("ai worklog telegram is not configured; stored local record only")
        return 0

    if not record.get("topic_id"):
        ensured = ensure_topic(token, chat_id, topic_name, project_ctx, config)
        record["topic_id"] = ensured.get("message_thread_id")
        record["topic_status"] = ensured.get("status")

    text = format_telegram_html(
        record,
        show_files=bool_config(config, "AI_WORKLOG_SHOW_FILES", default=False),
        show_git=bool_config(config, "AI_WORKLOG_SHOW_GIT", default=False),
    )
    ok = send_telegram(token, chat_id, text, record.get("topic_id"))
    record["telegram_send_ok"] = ok
    record["telegram_status"] = "sent" if ok else "send_failed"
    record["telegram_sent_at"] = now_iso()
    if not args.no_local_log:
        append_worklog(record)
    return 0 if ok else 1


def build_record(
    args: argparse.Namespace,
    project_ctx: dict[str, Any],
    topic_name: str,
    topic_id: str | None,
) -> dict[str, Any]:
    git = git_info(project_ctx.get("git_root") or os.getcwd())
    return {
        "timestamp": now_iso(),
        "nonce": args.nonce or generate_nonce(),
        "project": project_ctx["project"],
        "topic_name": topic_name,
        "topic_id": topic_id,
        "session_id": session_id(args.session_id),
        "cwd": os.getcwd(),
        "git_root": project_ctx.get("git_root"),
        "git": git,
        "user_summary": clean_text(args.user_summary or "요청 요약 미기재"),
        "answer_summary": clean_text(args.answer_summary or "답변 요약 미기재"),
        "changes": clean_text(args.changes or auto_changes_summary(git)),
    }


def project_context(project: str | None = None) -> dict[str, Any]:
    git_root = run_text(["git", "rev-parse", "--show-toplevel"])
    root_path = pathlib.Path(git_root).resolve() if git_root else pathlib.Path.cwd().resolve()
    project_name = project or root_path.name or pathlib.Path.cwd().name
    return {"project": project_name, "git_root": str(root_path)}


def git_info(cwd: str) -> dict[str, Any]:
    branch = run_text(["git", "branch", "--show-current"], cwd=cwd) or "detached"
    head = run_text(["git", "rev-parse", "--short", "HEAD"], cwd=cwd)
    status_raw = run_text(["git", "status", "--short"], cwd=cwd)
    status_lines = status_raw.splitlines() if status_raw else []
    return {
        "branch": branch,
        "head": head,
        "dirty": bool(status_lines),
        "changed_count": len(status_lines),
        "changed_files": status_lines[:20],
    }


def auto_changes_summary(git: dict[str, Any]) -> str:
    files = git.get("changed_files") or []
    if not files:
        return "파일 변경 없음 또는 확인된 변경 없음"
    shown = ", ".join(files[:8])
    suffix = f" 외 {len(files) - 8}개" if len(files) > 8 else ""
    return f"git status 변경: {shown}{suffix}"


def ensure_topic(
    token: str,
    chat_id: str,
    topic_name: str,
    project_ctx: dict[str, Any],
    config: dict[str, str],
) -> dict[str, Any]:
    topic_map = read_topic_map(config)
    chat_key = str(chat_id)
    topics = topic_map.setdefault("chats", {}).setdefault(chat_key, {})
    existing = topics.get(topic_name)
    if existing and existing.get("message_thread_id"):
        return {
            "status": "mapped",
            "topic_name": topic_name,
            "message_thread_id": str(existing["message_thread_id"]),
        }

    if not bool_config(config, "AI_WORKLOG_AUTO_CREATE_TOPICS", default=True):
        return {"status": "missing", "topic_name": topic_name, "message_thread_id": None}

    response = telegram_api(
        token,
        "createForumTopic",
        {"chat_id": chat_id, "name": topic_name},
    )
    result = response.get("result") if response.get("ok") else None
    if not isinstance(result, dict) or not result.get("message_thread_id"):
        log(f"createForumTopic failed: {safe_json(response)}")
        if bool_config(config, "AI_WORKLOG_FALLBACK_TO_GENERAL", default=True):
            return {
                "status": "create_failed_general_fallback",
                "topic_name": topic_name,
                "message_thread_id": None,
            }
        raise SystemExit(1)

    message_thread_id = str(result["message_thread_id"])
    topics[topic_name] = {
        "message_thread_id": message_thread_id,
        "project": project_ctx.get("project"),
        "git_root_hash": short_hash(project_ctx.get("git_root") or ""),
        "created_at": now_iso(),
    }
    write_topic_map(config, topic_map)
    return {
        "status": "created",
        "topic_name": topic_name,
        "message_thread_id": message_thread_id,
    }


def format_telegram_html(
    record: dict[str, Any],
    show_files: bool = False,
    show_git: bool = False,
) -> str:
    git = record.get("git") or {}
    changed = git.get("changed_files") or []
    changed_line = ""
    if show_files and changed:
        changed_line = "\n<b>files</b>: " + h(", ".join(changed[:6]))
        if len(changed) > 6:
            changed_line += h(f" 외 {len(changed) - 6}개")

    dirty = "dirty" if git.get("dirty") else "clean"
    git_line = ""
    if show_git:
        git_line = (
            f"\n<b>git</b>: <code>{h(git.get('branch') or '?')}@{h(git.get('head') or '?')}</code> "
            f"<code>{dirty}</code>"
        )
    text = (
        f"<b>AI Worklog</b> <code>{h(record['project'])}</code>\n"
        f"<b>user</b>: {h(limit(record.get('user_summary') or '', 700))}\n"
        f"<b>answer</b>: {h(limit(record.get('answer_summary') or '', 900))}\n"
        f"<b>changes</b>: {h(limit(record.get('changes') or '', 900))}\n"
        f"<b>nonce</b>: <code>{h(record['nonce'])}</code>\n"
        f"<b>session</b>: <code>{h(record['session_id'])}</code>"
        f"{git_line}"
        f"{changed_line}"
    )
    return limit(text, 3900)


def print_updates(config: dict[str, str]) -> int:
    token = first_value(config, BOT_TOKEN_KEYS)
    if not token:
        print("Missing AI_WORKLOG_BOT_TOKEN in private config.", file=sys.stderr)
        return 1
    response = telegram_api(token, "getUpdates", {"limit": 20, "allowed_updates": json.dumps(["message", "channel_post"] )})
    if not response.get("ok"):
        print(safe_json(response), file=sys.stderr)
        return 1
    sanitized = []
    for update in response.get("result") or []:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        sanitized.append(
            {
                "update_id": update.get("update_id"),
                "chat_id": chat.get("id"),
                "chat_title": chat.get("title"),
                "chat_type": chat.get("type"),
                "is_forum": chat.get("is_forum"),
                "message_thread_id": message.get("message_thread_id"),
                "forum_topic_created": bool(message.get("forum_topic_created")),
                "date": message.get("date"),
            }
        )
    print(json.dumps(sanitized, ensure_ascii=False, indent=2))
    return 0


def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    message_thread_id: str | int | None = None,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if message_thread_id:
        payload["message_thread_id"] = str(message_thread_id)
    response = telegram_api(bot_token, "sendMessage", payload)
    if not response.get("ok"):
        log(f"telegram send failed: {safe_json(response)}")
        return False
    return True


def telegram_api(bot_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"ok": False, "result": parsed}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def load_config() -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in os.environ.items():
        values[key] = value
        values[key.upper()] = value

    file_path = values.get("AI_WORKLOG_ENV_FILE") or values.get("LLM_NOTI_FILE") or values.get("LLM_NOTI_ENV_FILE")
    candidates: list[pathlib.Path] = []
    if file_path:
        candidates.append(pathlib.Path(file_path).expanduser())
    candidates.extend(
        [
            pathlib.Path.home() / ".codex" / ("telegram_notify." + "env"),
            pathlib.Path.home() / ".codex" / DOTENV_NAME,
            pathlib.Path.home() / DOTENV_NAME,
            pathlib.Path.cwd() / DOTENV_NAME,
        ]
    )

    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        values.update(parse_secret_file(candidate))
    return values


def parse_secret_file(path: pathlib.Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log(f"could not read config file {path}: {exc}")
        return parsed

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if not key:
            continue
        value = value.strip()
        try:
            parts = shlex.split(value, comments=False, posix=True)
            value = parts[0] if parts else ""
        except Exception:
            value = value.strip("'\"")
        parsed[key] = value
        parsed[key.upper()] = value
    return parsed


def read_topic_map(config: dict[str, str]) -> dict[str, Any]:
    path = topic_map_path(config)
    if not path.exists():
        return {"version": 1, "chats": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {"version": 1, "chats": {}}
    except Exception as exc:
        log(f"could not read topic map {path}: {exc}")
        return {"version": 1, "chats": {}}


def write_topic_map(config: dict[str, str], data: dict[str, Any]) -> None:
    path = topic_map_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def topic_map_path(config: dict[str, str]) -> pathlib.Path:
    raw = config.get("AI_WORKLOG_TOPIC_MAP") or config.get("AI_WORKLOG_TOPIC_MAP_FILE")
    return pathlib.Path(raw).expanduser() if raw else TOPIC_MAP_FILE


def append_worklog(record: dict[str, Any]) -> None:
    WORKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with WORKLOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def first_value(config: dict[str, str], keys: list[str]) -> str | None:
    for key in keys:
        value = config.get(key)
        if value:
            return str(value)
    return None


def bool_config(config: dict[str, str], key: str, default: bool = False) -> bool:
    value = config.get(key)
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def is_disabled(config: dict[str, str]) -> bool:
    value = str(config.get("AI_WORKLOG_ENABLED", "true")).strip().lower()
    return value in {"0", "false", "no", "off"}


def session_id(explicit: str | None = None) -> str:
    for value in (
        explicit,
        os.environ.get("CODEX_THREAD_ID"),
        os.environ.get("CODEX_SESSION_ID"),
        os.environ.get("OPENAI_THREAD_ID"),
    ):
        if value:
            return str(value)
    return f"missing-session-{socket.gethostname()}-{os.getppid()}"


def generate_nonce() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def sanitize_topic_name(value: str) -> str:
    cleaned = re.sub(r"[\r\n\t]+", " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "unknown-project"


def clean_text(value: str) -> str:
    cleaned = value.replace("\r", " ").strip()
    for pattern, replacement in SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def h(value: Any) -> str:
    return html.escape(str(value), quote=False)


def limit(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def safe_json(value: Any) -> str:
    return clean_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run_text(cmd: list[str], cwd: str | None = None) -> str | None:
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def log(message: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{now_iso()} {clean_text(message)}\n")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())

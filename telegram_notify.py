#!/usr/bin/env python3
"""
Explicit Codex completion notifier for Telegram.

This script intentionally never prints or stores Telegram secrets. It exits with 0
even when notification is not configured so Codex work is not blocked.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import sys
import time
import urllib.parse
import urllib.request


STATE_DIR = pathlib.Path.home() / ".local" / "state" / "codex-telegram-notify"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "notify.log"

DOTENV_NAME = "." + "env"

BOT_TOKEN_KEYS = [
    "TELEGRAM_LLM_NOTI_BOT_TOKEN",
    "LLM_NOTI_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN",
]

OWNER_ID_KEYS = [
    "OWNER_ACCOUNT_ID",
    "TELEGRAM_OWNER_ACCOUNT_ID",
    "LLM_NOTI_OWNER_ACCOUNT_ID",
    "TELEGRAM_CHAT_ID",
    "CHAT_ID",
]

WORKLOG_CHAT_ID_KEYS = [
    "AI_WORKLOG_CHAT_ID",
    "TELEGRAM_WORKLOG_CHAT_ID",
    "WORKLOG_CHAT_ID",
    "TELEGRAM_GROUP_CHAT_ID",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--send-now",
        action="store_true",
        help="send one notification immediately; intended for explicit task completion",
    )
    parser.add_argument(
        "--summary",
        help="short description of the completed work for --send-now",
    )
    parser.add_argument(
        "--message",
        help="backward-compatible alias for --summary",
    )
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    hook_event = read_hook_event()
    config = load_config()
    if is_disabled(config):
        return 0

    if not first_value(config, BOT_TOKEN_KEYS) or not first_value(config, OWNER_ID_KEYS):
        log("telegram notifier is not configured; missing bot token or owner id")
        return 0

    if args.send_now:
        summary = args.summary or args.message
        if should_skip_legacy_dm(config):
            write_json(
                STATE_FILE,
                {
                    "mode": "legacy-dm-skipped",
                    "cwd": os.getcwd(),
                    "summary": summary,
                    "thread_id": codex_thread_id(),
                    "last_skipped_at": time.time(),
                    "reason": "ai-worklog-topic-enabled",
                },
            )
            log("legacy DM completion notifier skipped because AI Worklog topic is configured")
            return 0
        ok = send_now(config, summary)
        write_json(
            STATE_FILE,
            {
                "mode": "send-now",
                "cwd": os.getcwd(),
                "summary": summary,
                "thread_id": codex_thread_id(),
                "last_sent_at": time.time(),
                "last_send_ok": ok,
            },
        )
        return 0 if ok else 1

    tool = tool_name(hook_event)
    log(f"telegram notifier ignored non-completion invocation from tool={tool}")
    return 0


def send_now(config: dict, message: str | None) -> bool:
    bot_token = first_value(config, BOT_TOKEN_KEYS)
    owner_id = first_value(config, OWNER_ID_KEYS)
    if not bot_token or not owner_id:
        return False
    summary = (message or "작업 완료").strip()
    thread_id = codex_thread_id()
    thread_line = (
        f"\\- 세션: `{escape_markdown_v2_code(thread_id)}`\n" if thread_id else ""
    )
    text = (
        "Codex 작업 완료\n"
        f"\\- 내용: {escape_markdown_v2(summary)}\n"
        f"\\- 위치: {escape_markdown_v2(os.getcwd())}\n"
        f"{thread_line}"
        "\\- 상태: 최종 응답 직전 명시적 완료 알림"
    )
    return send_telegram(bot_token, owner_id, text)


def codex_thread_id() -> str | None:
    value = os.environ.get("CODEX_THREAD_ID")
    if value:
        return value
    return None


def read_hook_event() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def load_config() -> dict:
    values = {}
    for key, value in os.environ.items():
        values[key] = value
        values[key.upper()] = value

    file_path = values.get("LLM_NOTI_FILE") or values.get("LLM_NOTI_ENV_FILE")
    candidates = []
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
        if first_value(values, BOT_TOKEN_KEYS) and first_value(values, OWNER_ID_KEYS):
            break

    return values


def parse_secret_file(path: pathlib.Path) -> dict:
    parsed = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log(f"could not read secret file {path}: {exc}")
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
            value = shlex.split(value, comments=False, posix=True)[0]
        except Exception:
            value = value.strip("'\"")
        parsed[key] = value
        parsed[key.upper()] = value
    return parsed


def first_value(config: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = config.get(key)
        if value:
            return str(value)
    return None


def is_disabled(config: dict) -> bool:
    value = str(config.get("LLM_NOTI_ENABLED", "true")).lower()
    return value in {"0", "false", "no", "off"}


def bool_config(config: dict, key: str, default: bool = False) -> bool:
    value = config.get(key)
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def should_skip_legacy_dm(config: dict) -> bool:
    if bool_config(config, "LLM_NOTI_LEGACY_DM_ENABLED", default=False):
        return False
    if bool_config(config, "AI_WORKLOG_ONLY", default=False):
        return True
    return bool(first_value(config, WORKLOG_CHAT_ID_KEYS))


def tool_name(event: dict) -> str:
    for key in ("tool_name", "toolName", "tool", "name"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def escape_markdown_v2(value: str) -> str:
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in special else char for char in value)


def escape_markdown_v2_code(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`")


def send_telegram(bot_token: str, owner_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": owner_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            ok = 200 <= response.status < 300
            if not ok:
                log(f"telegram send failed with status {response.status}")
            return ok
    except Exception as exc:
        log(f"telegram send failed: {exc}")
        return False


def write_json(path: pathlib.Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def log(message: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())

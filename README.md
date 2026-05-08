# codex_noti_bot

This script sends a Telegram message when Codex explicitly marks a task complete.

MCP and skills are not the right primitive for automatic completion signals:

- MCP exposes tools the model can call.
- Skills guide model behavior.
- Hooks run automatically around Codex events, but this Codex build does not expose a verified final-answer hook.

## Secret File

Install the script first:

```bash
git clone https://github.com/NA-DEGEN-GIRL/codex_noti_bot.git
cd codex_noti_bot
./install.sh
```

Create a private secret file:

```bash
nano ~/.codex/telegram_notify.env
chmod 600 ~/.codex/telegram_notify.env
```

The script can load the private values from `LLM_NOTI_FILE`, or from common private files under the home and Codex config directories. Do not commit the real secret file.

Supported key names:

```text
TELEGRAM_LLM_NOTI_BOT_TOKEN
LLM_NOTI_BOT_TOKEN
TELEGRAM_BOT_TOKEN
BOT_TOKEN
OWNER_ACCOUNT_ID
TELEGRAM_OWNER_ACCOUNT_ID
LLM_NOTI_OWNER_ACCOUNT_ID
TELEGRAM_CHAT_ID
CHAT_ID
```

## Behavior

Codex currently has `PreToolUse`, `PostToolUse`, and `UserPromptSubmit` hook events configured in this environment. There is no verified "final answer sent" hook here, so this notifier is not installed as an automatic idle hook.

For exact completion semantics, run this immediately before the final response:

```bash
python3 /home/na_stream/.codex/hooks/telegram_notify.py --send-now
```

Portable path:

```bash
python3 ~/.codex/hooks/telegram_notify.py --send-now --summary "작업 요약"
```

Optional custom message:

```bash
python3 /home/na_stream/.codex/hooks/telegram_notify.py --send-now --summary "Telegram 완료 알림 형식 개선"
```

Invoking the script without `--send-now` exits without sending a message, so it cannot fire early from ordinary tool activity.

The Telegram body always includes:

```text
Codex 작업 완료
- 내용: <summary>
- 위치: <cwd>
- 세션: `<CODEX_THREAD_ID, when available>`
- 상태: 최종 응답 직전 명시적 완료 알림
```

The session id is sent as Telegram MarkdownV2 inline code so it is easy to tap or copy.

## Codex Instruction

Add this to your global Codex instructions on each machine:

```text
작업을 완료하고 final 답변을 보내기 직전에 다음 명령으로 Telegram 알림을 보낸다:
python3 ~/.codex/hooks/telegram_notify.py --send-now --summary "<완료한 작업 요약>"
```

## Owner-Only Use

This notifier only sends messages to `OWNER_ACCOUNT_ID`. It does not run an inbound bot command server, so there is no chat command surface for other users. Keep the bot token out of git; anyone with the token can send messages as that bot.

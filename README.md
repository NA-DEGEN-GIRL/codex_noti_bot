# codex_noti_bot

Telegram helpers for Codex work sessions.

This repo installs two small scripts:

- `telegram_notify.py` — sends an explicit "Codex task complete" Telegram message.
- `ai_worklog.py` — records each AI work turn with project, session, nonce, summaries, git state, and optional Telegram forum-topic delivery.

For Codex, the recommended default is now **AI Worklog only**. The older direct-message completion notifier remains available for legacy/manual tests, but normal Codex sessions should use the project Telegram topic worklog.

It is designed for **exact worklog semantics**. It does not rely on idle timers or automatic "maybe done" hooks.

## What it solves

Long AI-assisted coding sessions can become hard to follow even when git is used.

Git answers:

- what files changed,
- when commits happened,
- what the diff contains.

This tool adds the missing AI workflow layer:

- what the user asked,
- what the AI understood/resulted,
- which project and session it happened in,
- a per-turn nonce for easy reference,
- a Telegram topic timeline per project.

## Installed layout

Running `./install.sh` copies files into Codex home:

```text
~/.codex/hooks/telegram_notify.py
~/.codex/hooks/ai_worklog.py
~/.codex/global_instructions.md
~/.codex/skills/ai-worklog/SKILL.md
```

Runtime state is kept outside the repo:

```text
~/.local/state/codex-ai-worklog/worklog.jsonl
~/.local/state/codex-ai-worklog/topics.json
~/.local/state/codex-telegram-notify/
```

## Install

```bash
git clone https://github.com/NA-DEGEN-GIRL/codex_noti_bot.git
cd codex_noti_bot
./install.sh
```

Create a private config file:

```bash
nano ~/.codex/telegram_notify.env
chmod 600 ~/.codex/telegram_notify.env
```

Do not commit the real config file.

## Private config

Minimal completion-notification config:

```text
TELEGRAM_LLM_NOTI_BOT_TOKEN=replace_with_bot_token
OWNER_ACCOUNT_ID=replace_with_owner_or_private_chat_id
LLM_NOTI_ENABLED=true
# Set true only when you explicitly want the old direct-message completion ping.
LLM_NOTI_LEGACY_DM_ENABLED=false
```

AI worklog forum-topic config:

```text
AI_WORKLOG_BOT_TOKEN=replace_with_worklog_bot_token
AI_WORKLOG_CHAT_ID=replace_with_forum_supergroup_chat_id_like_-1001234567890
AI_WORKLOG_AUTO_CREATE_TOPICS=true
AI_WORKLOG_ENABLED=true
AI_WORKLOG_ONLY=true
```

If `AI_WORKLOG_BOT_TOKEN` is omitted, `ai_worklog.py` falls back to the completion-notifier bot token keys.

Optional:

```text
# Force all worklogs into one known topic instead of per-project topics.
AI_WORKLOG_TOPIC_ID=replace_with_message_thread_id

# Default false. Telegram stays compact; local JSONL still stores changed files.
AI_WORKLOG_SHOW_FILES=false

# Default false. Telegram stays compact; local JSONL still stores git state.
AI_WORKLOG_SHOW_GIT=false

# Custom topic map path.
AI_WORKLOG_TOPIC_MAP=~/.local/state/codex-ai-worklog/topics.json
```

Supported completion bot token aliases:

```text
TELEGRAM_LLM_NOTI_BOT_TOKEN
LLM_NOTI_BOT_TOKEN
TELEGRAM_BOT_TOKEN
BOT_TOKEN
```

Supported completion chat/user id aliases:

```text
OWNER_ACCOUNT_ID
TELEGRAM_OWNER_ACCOUNT_ID
LLM_NOTI_OWNER_ACCOUNT_ID
TELEGRAM_CHAT_ID
CHAT_ID
```

## Telegram topic setup

For project topics, use a Telegram forum-enabled supergroup.

Checklist:

1. Create or choose a Telegram bot.
2. Create a supergroup with topics enabled.
3. Add the bot to the group.
4. Give the bot topic-management permission.
5. Put the group chat id in `AI_WORKLOG_CHAT_ID`.

Discover chat/topic ids:

```bash
python3 ~/.codex/hooks/ai_worklog.py --print-updates
```

Create or confirm a project topic:

```bash
python3 ~/.codex/hooks/ai_worklog.py --ensure-topic --project codex_noti_bot
```

The project-to-topic mapping is cached locally in `topics.json`.

## Usage

### Legacy: send a direct-message completion notification

```bash
python3 ~/.codex/hooks/telegram_notify.py --send-now --summary "작업 요약"
```

The Telegram message includes:

```text
Codex 작업 완료
- 내용: <summary>
- 위치: <cwd>
- 세션: <CODEX_THREAD_ID, when available>
- 상태: 최종 응답 직전 명시적 완료 알림
```

### Send an AI worklog turn

```bash
python3 ~/.codex/hooks/ai_worklog.py --send-turn \
  --user-summary "사용자 요청 요약" \
  --answer-summary "AI 답변/결과 요약" \
  --changes "변경/검증 요약"
```

The script automatically adds:

- project name from git root folder,
- session id from `CODEX_THREAD_ID` when available,
- per-turn nonce,
- git branch/head/dirty state,
- local JSONL record.

Default Telegram order is optimized for reading:

```text
AI Worklog <project>
user
answer
changes
nonce
session
```

Git state and changed-file lists stay in local JSONL by default. Enable `AI_WORKLOG_SHOW_GIT=true` or `AI_WORKLOG_SHOW_FILES=true` only if you want those details in Telegram too.

Dry run:

```bash
python3 ~/.codex/hooks/ai_worklog.py --send-turn --dry-run \
  --user-summary "test" \
  --answer-summary "test" \
  --changes "none"
```

## Recommended Codex instruction

Put an `AGENTS.md` above the repos you want covered, or use `model_instructions_file` in Codex config.

Recommended finalization:

```text
Before the final response:

Record an AI Worklog turn:
python3 ~/.codex/hooks/ai_worklog.py --send-turn --user-summary "<request summary>" --answer-summary "<answer/result summary>" --changes "<changes/verification summary>"
```

Do not also send the old direct-message completion notifier for Codex sessions unless explicitly requested. When `AI_WORKLOG_CHAT_ID` is configured, `telegram_notify.py --send-now` skips the legacy DM by default; set `LLM_NOTI_LEGACY_DM_ENABLED=true` only for a legacy DM test.

This repo includes `codex_global_instructions.md` as a reusable template.

Already-running Codex sessions may not reload changed instruction files. Start a fresh Codex process when you need to confirm new global behavior.

## Privacy and safety

- Never commit real bot tokens, chat ids, account ids, or private config files.
- Keep worklog summaries compact; do not paste raw secrets or raw private config values.
- Anyone who can read the Telegram forum topic can read the worklog summaries.
- `ai_worklog.py` redacts common token/key patterns, but summaries should still be written carefully.
- The scripts do not run an inbound bot command server.

## Why explicit commands?

This Codex environment has tool hooks such as `PreToolUse`, `PostToolUse`, and `UserPromptSubmit`, but no verified "final answer sent" hook. Automatic idle/debounce detection can fire early.

For that reason, this repo uses an explicit AI Worklog finalization command instead of guessing when work is complete.

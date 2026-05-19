---
name: ai-worklog
description: Record AI work as a project/session/nonce ledger and send compact turn summaries to Telegram forum topics. Use when the user asks for AI-friendly version/workflow tracking, Telegram topic worklogs, per-session/per-turn nonces, or durable summaries of user request, AI answer, and changed files.
metadata:
  short-description: Send AI work summaries to Telegram topics
---

# AI Worklog

Use this skill when the user wants AI work to be traceable beyond git commits.
Git records file history; this worklog records intent, context, summaries, and session flow.

## Finalization workflow

Before the final response for any non-trivial repo/setup/debugging task, run exactly one AI Worklog command:

```bash
python3 ~/.codex/hooks/ai_worklog.py --send-turn \
  --user-summary "<compact summary of the user's request>" \
  --answer-summary "<compact summary of what you will report>" \
  --changes "<files changed, commands run, or no-change result>"
```

Do not also send the old direct-message completion notifier for Codex sessions unless the user explicitly asks for a legacy DM test. The Telegram topic worklog is the default and only persistent Codex signal.

## Required content

- `project`: let the script infer it from the git root folder unless the user asks otherwise.
- `session`: let the script use `CODEX_THREAD_ID`; pass `--session-id` only for manual/offline runs.
- `nonce`: let the script generate it; pass `--nonce` only when replaying a known record.
- `user-summary`: summarize the user request, not the entire raw prompt.
- `answer-summary`: summarize the final answer/result.
- `changes`: include changed paths, verification commands, or explicitly say no files changed.

## Privacy rules

- Do not include secrets, tokens, phone numbers, private account ids, or raw dotenv values.
- Prefer summaries over raw transcripts.
- If a secret-like value appeared in the request/output, write `<redacted>`.
- For public packaging, keep local usernames/home paths out of committed docs unless they are already repo-specific and intentional.

## Telegram topic behavior

The installed script sends to one forum topic per project folder. Topic ids are cached locally under `~/.local/state/codex-ai-worklog/topics.json`. If the bot has topic-management permission and `AI_WORKLOG_AUTO_CREATE_TOPICS` is not disabled, missing project topics are created automatically.

Telegram output is intentionally compact and ordered for reading: `AI Worklog`, `user`, `answer`, `changes`, `nonce`, `session`. Git state and changed file lists are kept in local JSONL, but not shown in Telegram unless `AI_WORKLOG_SHOW_GIT=true` or `AI_WORKLOG_SHOW_FILES=true`.

Useful setup/debug commands:

```bash
python3 ~/.codex/hooks/ai_worklog.py --print-updates
python3 ~/.codex/hooks/ai_worklog.py --ensure-topic --project "my-project"
python3 ~/.codex/hooks/ai_worklog.py --send-turn --dry-run --user-summary "test" --answer-summary "test" --changes "none"
```

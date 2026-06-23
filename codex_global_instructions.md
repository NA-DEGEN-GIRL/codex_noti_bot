# Global Codex Instructions

Before sending a final response after completing a user request, record one compact AI Worklog turn to the project Telegram topic.

```bash
python3 ~/.codex/hooks/ai_worklog.py --send-turn --user-summary "<short summary of the user's request>" --answer-summary "<short summary of the final answer/result>" --changes "<files changed, commands run, or no files changed>"
```

Use concise summaries. Do not include secrets, raw tokens, phone numbers, private account ids, or raw dotenv values. The script generates the per-turn nonce and includes the Codex session id when available.

Do not send the old direct-message completion notification for Codex sessions unless the user explicitly asks for a legacy DM test. AI Worklog topic messages are the default and only persistent Codex completion/worklog signal.

If the AI Worklog command fails, mention that the worklog failed and include the failure reason in the final response.

Each `--send-turn` now also captures the full working tree (tracked + untracked) into a `refs/worklog/<nonce>` git ref, so any turn is restorable even without a manual commit. When the user gives you a nonce and asks to resume/restore previous work, run ONE command instead of reconstructing the state by hand:

```bash
python3 ~/.codex/hooks/ai_worklog.py --restore <nonce>
```

This prints a context briefing (user/answer/changes/git base) and overlays that turn's working tree (after auto-backing up the current state to a `refs/worklog-backup/` ref; restore aborts rather than overwrite if that backup fails, unless you pass `--force`). It never deletes files. Add `--dry-run` to preview without applying. If you don't have the nonce, run `python3 ~/.codex/hooks/ai_worklog.py --list` to see recent restorable nonces. If a nonce has no snapshot, you get a context-only briefing. Read the briefing first, then continue from there — do not re-derive the prior state by guessing.

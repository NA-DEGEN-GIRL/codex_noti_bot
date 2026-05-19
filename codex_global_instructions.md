# Global Codex Instructions

Before sending a final response after completing a user request, record one compact AI Worklog turn to the project Telegram topic.

```bash
python3 ~/.codex/hooks/ai_worklog.py --send-turn --user-summary "<short summary of the user's request>" --answer-summary "<short summary of the final answer/result>" --changes "<files changed, commands run, or no files changed>"
```

Use concise summaries. Do not include secrets, raw tokens, phone numbers, private account ids, or raw dotenv values. The script generates the per-turn nonce and includes the Codex session id when available.

Do not send the old direct-message completion notification for Codex sessions unless the user explicitly asks for a legacy DM test. AI Worklog topic messages are the default and only persistent Codex completion/worklog signal.

If the AI Worklog command fails, mention that the worklog failed and include the failure reason in the final response.

# Global Codex Instructions

Before sending a final response after completing a user request, run the Telegram completion notifier:

```bash
python3 ~/.codex/hooks/telegram_notify.py --send-now --summary "<short completed-work summary>"
```

Use a concrete summary that says what was completed. This applies to code changes, setup work, repo maintenance, debugging, and answer-only requests. Run it as the final tool action immediately before the final response.

If the command fails, mention that the completion notification failed and include the failure reason in the final response.

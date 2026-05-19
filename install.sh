#!/usr/bin/env bash
set -euo pipefail

codex_home="${CODEX_HOME:-$HOME/.codex}"
install_dir="$codex_home/hooks"
skill_dir="$codex_home/skills/ai-worklog"
mkdir -p "$install_dir" "$skill_dir"

install -m 700 telegram_notify.py "$install_dir/telegram_notify.py"
install -m 700 ai_worklog.py "$install_dir/ai_worklog.py"
install -m 600 README.md "$install_dir/telegram_notify.README.md"
install -m 600 telegram_notify.conf.example "$install_dir/telegram_notify.conf.example"
install -m 600 codex_global_instructions.md "$codex_home/global_instructions.md"
install -m 600 skills/ai-worklog/SKILL.md "$skill_dir/SKILL.md"

echo "Installed completion notifier to $install_dir/telegram_notify.py"
echo "Installed AI worklog sender to $install_dir/ai_worklog.py"
echo "Installed ai-worklog skill to $skill_dir/SKILL.md"
echo "Create/update private Telegram config at $codex_home/telegram_notify.env before testing sends."
echo "Optional: add model_instructions_file = \"$codex_home/global_instructions.md\" to ~/.codex/config.toml."

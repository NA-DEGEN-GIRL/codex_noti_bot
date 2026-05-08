#!/usr/bin/env bash
set -euo pipefail

install_dir="${CODEX_HOME:-$HOME/.codex}/hooks"
mkdir -p "$install_dir"

install -m 700 telegram_notify.py "$install_dir/telegram_notify.py"
install -m 600 README.md "$install_dir/telegram_notify.README.md"
install -m 600 telegram_notify.conf.example "$install_dir/telegram_notify.conf.example"
install -m 600 codex_global_instructions.md "${CODEX_HOME:-$HOME/.codex}/global_instructions.md"

echo "Installed Telegram notifier to $install_dir/telegram_notify.py"
echo "Create a private secret file at $install_dir/../telegram_notify.env before testing."
echo "Optional: add model_instructions_file = \"$install_dir/../global_instructions.md\" to ~/.codex/config.toml."

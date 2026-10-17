#!/usr/bin/env bash
# Restart Timosheeto web (:8090) and Telegram bot. Invoked via sudo (see sudoers).
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -n "${HOME}/redmine-sync/deploy/restart-services.sh" "$@"
fi
systemctl restart redmine-sync-web.service redmine-sync-bot.service

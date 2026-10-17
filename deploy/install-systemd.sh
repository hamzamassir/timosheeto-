#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -n bash "$0" "$@"
fi
REPO="/home/hamza/redmine-sync"
cp "${REPO}/deploy/redmine-sync-web.service" /etc/systemd/system/
cp "${REPO}/deploy/redmine-sync-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable redmine-sync-web.service redmine-sync-bot.service
systemctl restart redmine-sync-web.service redmine-sync-bot.service
echo "redmine-sync-web and redmine-sync-bot are enabled and running."

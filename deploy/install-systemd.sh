#!/usr/bin/env bash
set -euo pipefail
REPO="${HOME}/redmine-sync"
sudo cp "${REPO}/deploy/redmine-sync-web.service" /etc/systemd/system/
sudo cp "${REPO}/deploy/redmine-sync-bot.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable redmine-sync-web.service redmine-sync-bot.service
echo "Installed. Start with:"
echo "  sudo systemctl restart redmine-sync-web redmine-sync-bot"
echo "  sudo systemctl status redmine-sync-web redmine-sync-bot"

#!/usr/bin/env bash
# Pull latest code and restart services (no password after fix-sudoers.sh).
set -euo pipefail
REPO="${HOME}/redmine-sync"
cd "${REPO}"
git pull --ff-only
exec sudo -n "${REPO}/deploy/restart-services.sh"

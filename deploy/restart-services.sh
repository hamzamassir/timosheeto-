#!/usr/bin/env bash
# Restart Timosheeto web (:8090) and Telegram bot. Invoked via sudo (see sudoers).
set -euo pipefail
REPO="${REPO:-/home/hamza/redmine-sync}"
PORT=8090
WEB_UNIT=redmine-sync-web.service

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -n "${REPO}/deploy/restart-services.sh" "$@"
fi

# Stop systemd first, then drop manual/no-hup web.py still holding :8090.
systemctl stop "${WEB_UNIT}" 2>/dev/null || true
sleep 1

pids_on_port() {
  if command -v ss >/dev/null 2>&1; then
    ss -H -tlnp "sport = :${PORT}" 2>/dev/null \
      | grep -oE 'pid=[0-9]+' \
      | cut -d= -f2 \
      | sort -u
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
  fi
}

is_timosheeto_web() {
  local pid="$1"
  [[ -r "/proc/${pid}/cmdline" ]] || return 1
  local cmd
  cmd="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  [[ "${cmd}" == *"${REPO}/web.py"* ]] || [[ "${cmd}" == *"redmine-sync"* && "${cmd}" == *"web.py"* ]]
}

kill_stale_web() {
  local pid cmd
  for pid in $(pids_on_port); do
    [[ -n "${pid}" ]] || continue
    if is_timosheeto_web "${pid}"; then
      cmd="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
      echo "Stopping stale Timosheeto web on :${PORT} (pid ${pid}): ${cmd}"
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in $(pids_on_port); do
    [[ -n "${pid}" ]] || continue
    if is_timosheeto_web "${pid}"; then
      echo "Force-killing pid ${pid} on :${PORT}"
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done
}

kill_stale_web

systemctl restart "${WEB_UNIT}" redmine-sync-bot.service
systemctl is-active --quiet "${WEB_UNIT}" || {
  echo "ERROR: ${WEB_UNIT} failed to start. Check: journalctl -u ${WEB_UNIT} -n 40 --no-pager"
  exit 1
}

#!/bin/bash
# Nightly encrypted off-host backup of member-created work and source settings. Run as root by workspace-backup.service.
# Imported source snapshots and credentials are excluded: sources can be downloaded again and members can sign in again.
set -euo pipefail
test "$(id -u)" = 0
set -a; . /etc/workspace/backup.env; set +a
: "${RESTIC_REPOSITORY:?}" "${RESTIC_PASSWORD:?}"
paths=()
for home in /home/*; do
  [ -d "$home/workspace/work" ] && paths+=("$home/workspace/work")
  [ -f "$home/.config/workspace/config.json" ] && paths+=("$home/.config/workspace/config.json")
done
restic cat config >/dev/null 2>&1 || restic init
if [ ${#paths[@]} -gt 0 ]; then
  restic backup --one-file-system --tag workspace "${paths[@]}"
fi
restic forget --tag workspace --keep-daily 7 --keep-weekly 4 --prune
restic check

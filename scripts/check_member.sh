#!/bin/bash
# Run as the member (for example by the member's agent): isolation, installed tooling and integrity of completed sources.
set -euo pipefail
test "$(id -u)" != 0
if sudo -n true 2>/dev/null; then echo 'FAIL: member has sudo'; exit 1; fi
test "$(stat -c %a "$HOME")" = 700
test ! -r /home/workspace-admin/.ssh/authorized_keys
test ! -w /opt/workspace/current
test "$(ps -eo user= | sort -u)" = "$(id -un)" || { echo 'FAIL: other users processes are visible'; exit 1; }
workspace-import doctor
for source in $(workspace-import status | python3 -c 'import json,sys; print(" ".join(k for k,v in json.load(sys.stdin).items() if v["current"]))'); do
  workspace-import verify "$source"
done
printf '%s\n' 'Member isolation, installed tooling and completed-source integrity checks passed.'

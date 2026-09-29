#!/bin/bash
# Read-only host checks, run by the administrator: ssh workspace-admin 'bash -s' < scripts/check_vm.sh
set -euo pipefail
sudo cloud-init status --wait
sudo test -f /var/lib/workspace/bootstrap-complete
sudo sshd -t
sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|allowgroups) '
test "$(sudo sshd -T | awk '/^permitrootlogin /{print $2}')" = no
test "$(findmnt -no LABEL /home)" = workspace-home || { echo 'FAIL: /home is not on the workspace-home volume'; exit 1; }
test "$(findmnt -no FSTYPE /tmp)" = tmpfs || { echo 'FAIL: /tmp is not memory-backed; reboot after setup-host.sh'; exit 1; }
findmnt -no OPTIONS /proc | grep -q hidepid=invisible
test "$(stat -c %a /home/workspace-admin)" = 700
sudo -n true
sudo ufw status verbose
systemctl is-enabled workspace-inventory.timer
test -z "$(systemctl --failed --no-legend)"
df -h / /home
free -h
printf '%s\n' 'Host checks passed.'

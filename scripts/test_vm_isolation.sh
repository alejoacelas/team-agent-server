#!/bin/bash
# Synthetic users are retained, password-locked, with no SSH keys or sudo grants.
set -euo pipefail
base=/var/lib/workspace-tests
sudo install -d -m 711 "$base"
for label in a b; do
  name="workspace-test-$label"
  if ! id "$name" >/dev/null 2>&1; then
    sudo useradd --system --home-dir "$base/$label" --shell /usr/sbin/nologin "$name"
  fi
  test "$(getent passwd "$name" | cut -d: -f6)" = "$base/$label"
  sudo install -d -m 700 -o "$name" -g "$name" "$base/$label"
  sudo -u "$name" sh -c 'umask 077; printf "synthetic fixture\n" > "$1/fixture.txt"' sh "$base/$label"
done
for label in a b; do
  other=a
  if [ "$label" = a ]; then other=b; fi
  name="workspace-test-$label"
  sudo -u "$name" test -r "$base/$label/fixture.txt"
  if sudo -u "$name" cat "$base/$other/fixture.txt" >/dev/null 2>&1; then
    echo 'FAIL: cross-user read succeeded'; exit 1
  fi
  if sudo -u "$name" sh -c 'echo changed >> "$1"' sh "$base/$other/fixture.txt" 2>/dev/null; then
    echo 'FAIL: cross-user write succeeded'; exit 1
  fi
  if sudo -u "$name" sudo -n true 2>/dev/null; then
    echo 'FAIL: synthetic member has sudo'; exit 1
  fi
  if sudo -u "$name" test -r /home/workspace-admin/.ssh/authorized_keys; then
    echo 'FAIL: admin private directory accessible'; exit 1
  fi
done
unit="workspace-synthetic-check-$(date +%s)"
sudo systemd-run --quiet --unit="$unit" --on-active=3s --timer-property=AccuracySec=1s --uid=workspace-test-a /bin/sh -c 'umask 077; printf "scheduled synthetic test\n" > "$1"' sh "$base/a/$unit.txt"
for attempt in {1..20}; do
  if sudo test -s "$base/a/$unit.txt"; then
    test "$(sudo stat -c %U "$base/a/$unit.txt")" = workspace-test-a
    test "$(sudo stat -c %a "$base/a/$unit.txt")" = 600
    echo 'PASS: own read/write, mutual read/write denial, no sudo, admin directory denial, scheduled execution as unprivileged user'
    echo 'Synthetic accounts and fixtures retained under /var/lib/workspace-tests; no source credentials or real records used.'
    exit 0
  fi
  sleep 1
done
echo 'FAIL: scheduled marker missing'; exit 1

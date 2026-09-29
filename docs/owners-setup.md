# Team agent server: setup steps for server owners

Steps 1–10 install the [default setup](owners-overview.md#the-default-install). The [optional add-ons](#optional-add-ons) follow.

You need: a DigitalOcean account with billing, Google Cloud project-creation rights in your organisation, Google Workspace admin access (or someone who has it), a password manager that can share items with one person, and a Mac or Linux terminal with `git` and `ssh`.

## Default setup

### 1. Get the code

```sh
git clone https://github.com/alejoacelas/team-agent-server.git
cd team-agent-server
```

### 2. Create the volume and the Droplet

In DigitalOcean, [create a Droplet](https://docs.digitalocean.com/products/droplets/how-to/create/) with:

| Setting | Value |
|---|---|
| Region | The one closest to your team, for example London (`LON1`) |
| Image | Ubuntu 24.04 (LTS) x64 |
| Size | See the [README](../README.md#cost-and-effort), for example Basic → 8 vCPU / 16 GB |
| Volume | Add a volume: 200–500 GB, named exactly `workspace-home`, **Manually Format & Mount** |
| Authentication | SSH key: your own public key |
| Backups | Off (they would skip the volume, so they'd hold no member data) |
| Monitoring | On |
| Hostname | `team-agent-server` |
| User data (Advanced options) | The full contents of [`infra/bootstrap.sh`](../infra/bootstrap.sh) |

The volume name matters: the setup script finds it at `/dev/disk/by-id/scsi-0DO_Volume_workspace-home`.

Then [create a Cloud Firewall](https://docs.digitalocean.com/products/networking/firewalls/how-to/create/) for the Droplet. Inbound: SSH (TCP 22) from all IPv4 and IPv6. Outbound: leave the default (all). The server's own firewall (`ufw`) also allows only SSH.

Finally, [set up monitoring alerts](https://docs.digitalocean.com/products/monitoring/how-to/set-up-alerts/) to the server owners' email for disk usage above 80% and memory above 90%.

### 3. Record the address

Copy the Droplet's public IPv4 address; it is `SERVER_IP` below.

### 4. Verify the server's identity

1. In DigitalOcean, open the Droplet's [Recovery or Droplet Console](https://docs.digitalocean.com/products/droplets/how-to/connect-with-console/) and run `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
2. On your computer, run `ssh-keyscan -t ed25519 SERVER_IP | tee ~/.ssh/workspace-known-hosts | ssh-keygen -lf -`.
3. The two `SHA256:` fingerprints must match.

Add this to `~/.ssh/config` on your computer:

```
Host workspace-admin
  HostName SERVER_IP
  User workspace-admin
  IdentityFile ~/.ssh/YOUR-KEY
  IdentitiesOnly yes
  UserKnownHostsFile ~/.ssh/workspace-known-hosts
  StrictHostKeyChecking yes
```

`ssh workspace-admin` should now connect; the first-boot script gave that account your key and `sudo`. `scripts/new_member.sh` later copies this verified host key into each member's setup.

### 5. Install the software and harden the host

From the repository folder:

```sh
bash scripts/deploy.sh
ssh workspace-admin 'sudo WORKSPACE_TIMEZONE=Europe/London bash /opt/workspace/current/infra/setup-host.sh && sudo reboot'
```

Set `WORKSPACE_TIMEZONE` to your team's timezone; it decides when the nightly 04:00 reboot happens, and defaults to UTC. `deploy.sh` installs the committed code as a new release under `/opt/workspace/releases/`. `setup-host.sh` moves `/home` onto the encrypted volume, puts `/tmp` in memory, hides processes between users, restricts SSH and turns on automatic security updates.

### 6. Create the Google OAuth app

1. In your organisation's Google Cloud, create a project named `team-agent-server`.
2. [Enable these APIs](https://developers.google.com/workspace/guides/enable-apis): Gmail, Google Calendar, Google Tasks, Google Drive, Google Docs and Google Forms. With `gcloud`:
   `gcloud services enable gmail.googleapis.com calendar-json.googleapis.com tasks.googleapis.com drive.googleapis.com docs.googleapis.com forms.googleapis.com --project team-agent-server`
3. [Configure the consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent) with **User type: Internal**. Add these scopes: `openid`, `userinfo.email`, `gmail.readonly`, `calendar.readonly`, `tasks.readonly`, `drive.readonly`, `documents.readonly`.
4. [Create an OAuth client](https://developers.google.com/workspace/guides/create-credentials#desktop-app) of type **Desktop app** and download its JSON file.
5. In the Google Workspace Admin console, check [API controls](https://support.google.com/a/answer/7281227). If Gmail or Drive access is restricted for third-party apps, mark this app's client ID as **Trusted**.
6. Install the file:

```sh
scp client_secret_*.json workspace-admin:/tmp/google-client.json
ssh workspace-admin 'sudo install -m 644 -o root -g root /tmp/google-client.json /etc/workspace/google-client.json && rm /tmp/google-client.json'
```

Google [doesn't treat desktop client secrets as confidential](https://developers.google.com/identity/protocols/oauth2/native-app); each member's refresh token, kept in their home, is what protects their data.

### 7. Check the host

```sh
ssh workspace-admin 'bash -s' < scripts/check_vm.sh
```

It must end with `Host checks passed.`

### 8. Fill in the member guide

Replace `[OWNERS_CONTACT]` in [`docs/member-guide.md`](member-guide.md) with how members reach you, for example a chat channel. Server details and usernames need no editing: `scripts/new_member.sh` writes them into each member's setup command.

### 9. Add each member

1. Choose a username: lowercase letters, digits and dashes, starting with a letter, for example `jane-doe`.
2. From the repository folder, run:

   ```sh
   bash scripts/new_member.sh jane-doe jane.doe@example.org
   ```

   This generates a key, creates the account on the server (private home, password login locked, agent guide installed as `~/AGENTS.md` and `~/CLAUDE.md`, monthly refresh on), and writes two files to `members/jane-doe/`.

3. In your password manager, create an item named **Team workspace – Jane Doe** and share it only with the member:
   - Attach `members/jane-doe/team-agent-server` as a file. Keep the name exactly `team-agent-server`, with no extension.
   - Paste the text of `members/jane-doe/setup-command.txt` into a field named **Setup command**.
4. Delete `members/jane-doe/`.
5. Send the member the guide and tell them the item is ready.

In their first session, the member's agent connects Google and runs the first downloads.

### 10. Confirm the member's setup

After the member's first session, ask them to have their agent run `bash /opt/workspace/current/scripts/check_member.sh`. It confirms that the member has no `sudo`, that their home is private, that other users' processes are hidden, and that every completed download passes its integrity check.

## Optional add-ons

### Backups of members' work

1. [Create a Spaces bucket](https://docs.digitalocean.com/products/spaces/how-to/create/) in the Droplet's region, named for example `workspace-backups-YOURORG`, with file listing **restricted**.
2. [Create a limited access key](https://docs.digitalocean.com/products/spaces/how-to/manage-access/) that covers only this bucket, with Read/Write/Delete permission.
3. Generate a backup password with `openssl rand -base64 32`. **Store it and the access key in your password manager.** Without the password, the backups cannot be restored.
4. Write the settings on the server and start the nightly timer:

```sh
ssh workspace-admin 'sudo install -m 600 /dev/null /etc/workspace/backup.env && sudo nano /etc/workspace/backup.env'
```

```
RESTIC_REPOSITORY=s3:https://REGION.digitaloceanspaces.com/workspace-backups-YOURORG
RESTIC_PASSWORD=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

```sh
ssh workspace-admin 'sudo systemctl enable --now workspace-backup.timer && sudo systemctl start workspace-backup.service && sudo journalctl -u workspace-backup.service -n 5'
```

The last output line should be `no errors were found`. To change how long backups are kept, edit `--keep-daily` and `--keep-weekly` in `infra/backup.sh` and redeploy. To restore a file, run `sudo bash -c 'set -a; . /etc/workspace/backup.env; restic restore latest --target /root/restore --include /home/USER/workspace/work'` and copy the result back with the member's ownership.

### Codex

```sh
ssh workspace-admin 'sudo bash /opt/workspace/current/infra/install-codex.sh'
```

The Codex app needs `codex` on the server ([docs](https://learn.chatgpt.com/docs/remote-connections)). Rerun this monthly, or sooner if the Codex app reports the server version is too old. In the pilot, both the Claude and Codex apps signed the member in on the server without help.

### Web and LinkedIn search

1. Create an API key at [dashboard.exa.ai](https://dashboard.exa.ai/api-keys) and set a monthly spending limit.
2. Install it where members' accounts can read it:

```sh
ssh workspace-admin 'sudo install -m 640 -o root -g workspace-users /dev/null /etc/workspace/exa-key && sudo nano /etc/workspace/exa-key'
```

3. Check it: `ssh workspace-admin 'sudo -u MEMBER workspace-import web-search "Anthropic" --results 1'` should print one result.

### Salesforce (untested)

1. Create a read-only integration user whose permissions cover exactly the records members may see.
2. Create an [External Client App](https://help.salesforce.com/s/articleView?id=xcloud.external_client_apps.htm) with the **OAuth client credentials flow** enabled, running as that user, with the `api` scope.
3. For each member who should have Salesforce, write `/home/USER/.config/workspace/salesforce.json`, owned by the member, mode 600:

```json
{"instance_url": "https://YOUR-DOMAIN.my.salesforce.com", "client_id": "…", "client_secret": "…"}
```

The member's agent then runs `workspace-import discover salesforce` and configures the objects to download.

### Airtable

1. From an Airtable account with read access to the bases members need, create a [personal access token](https://airtable.com/create/tokens) with the scopes `data.records:read` and `schema.bases:read`, limited to those bases.
2. For each member, write `/home/USER/.config/workspace/airtable.json` (member-owned, mode 600): `{"token": "…"}`.

### Slack app (sign-in not built yet)

Members can't connect Slack until `workspace-import connect-slack` is built. To have the app ready:

1. At [api.slack.com/apps](https://api.slack.com/apps), choose **Create New App → From a manifest**, pick your workspace and paste [`config/slack-app-manifest.json`](../config/slack-app-manifest.json).
2. Under **OAuth & Permissions**, confirm that PKCE is on and that the redirect URL is `http://localhost:8765/`.
3. Install the app to the workspace. If the workspace requires app approval, approve it as a Slack admin.
4. Save the Client ID on the server. It isn't secret: `ssh workspace-admin 'echo "{\"client_id\": \"CLIENT_ID\"}" | sudo tee /etc/workspace/slack-client.json'`

## Maintenance

- **Monthly:** read `/var/lib/workspace/inventory/latest.json`. It lists each member's sources, when each last completed and any new sources, without message contents or credentials. Check disk space with `df -h /home`. If you set up backups, run `sudo bash -c 'set -a; . /etc/workspace/backup.env; restic snapshots'` to confirm last night's backup exists.
- **Code updates:** pull the repository and run `bash scripts/deploy.sh`. Each release is kept under `/opt/workspace/releases/`. To roll back, point `/opt/workspace/current` at an earlier release.

## Removing a member or deleting data

1. Ask the member to remove the app at [myaccount.google.com/connections](https://myaccount.google.com/connections), or revoke its token for them in the Admin console under the user's security settings.
2. Stop and remove their account: `sudo systemctl disable --now workspace-refresh@USER.timer && sudo userdel -r USER`. This deletes their home, including downloaded data, working files and credentials.
3. If you set up backups, their work files leave the backups within about five weeks, when older copies expire. For an urgent deletion, run `restic forget` on the affected snapshots and then `restic prune`.
4. If their Mac is lost, first remove their key from `/home/USER/.ssh/authorized_keys`. To give them a new key, run `ssh-keygen` for a new pair, replace `authorized_keys` with the new public key, and send the private key through your password manager as in step 9.

Members' agents can delete a downloaded source themselves and stop it downloading again.

## Reference

- **Layout:** code releases in `/opt/workspace/releases/`, with `/opt/workspace/current` pointing at the active one. Command: `workspace-import`. Per member: data in `~/workspace/data/SOURCE/current`, notes in `~/workspace/work`, uploads in `~/workspace/incoming`. Settings and credentials in `~/.config/workspace/` (mode 600). A second copy of the Google token is kept in `~/.config/gdoc/accounts/EMAIL/`.
- **Scheduled jobs:** `workspace-refresh@USER.timer` (monthly, runs as the member, sandboxed to their home), `workspace-inventory.timer` (monthly metadata report), and `workspace-backup.timer` (nightly, only if you set up backups).
- **Tests:** `uv sync --frozen && uv run pytest -q`. On the server, `scripts/test_vm_isolation.sh` creates two locked test users and checks that neither can read the other's files.
- **Google sign-in:** the agent runs `workspace-import connect-google --start`, which prints a Google link. After approving, the member pastes back the address the browser failed to load. `--finish` then checks the one-time state value, exchanges the code using the verifier saved privately in the member's home (PKCE), and saves the token only if the Google account matches the member's email. Unfinished sign-ins expire after 15 minutes.

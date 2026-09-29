# Team agent server

A private server that gives each person on a team a read-only copy of their work data (Gmail, Calendar, Tasks and Drive, plus shared folders and optional CRM sources) as ordinary files. They analyse it with Claude Code or Codex running on the server instead of their laptop. It's built for organisations of 10–50 people on Google Workspace, with Macs.

Example of what a member can ask:

> I suspect clients who raised budget concerns in their first call were the ones who later stopped working with us. Check that across my call transcripts and follow-up emails, and show me a few examples of how you judged "budget concerns". Ask me questions to clarify before you start.

## What it solves

1. **Work across the whole history, not one lookup at a time.** Connectors in Claude or ChatGPT fetch a handful of emails or documents per request. Here the agent has every email, calendar entry and Drive file on disk, so it can search, script and classify thousands of items with ordinary tools (`rg`, `sqlite3`, Python). In the pilot, one person's Drive came to 2,534 items. Long jobs run in the background and report back when they're done.
2. **Keep the data under central control.** The data sits on one server the organisation owns, on an encrypted volume, with one Linux account per member so no one can read another member's files. Access to Google is read-only. The monthly refresh replaces the old copy, so anything deleted at the source leaves the server within a month. Offboarding someone means deleting their account. Server owners hold the only administrator access.
3. **Run the agent somewhere other than a laptop.** Members connect the Claude or Codex desktop app to the server over SSH, or use Claude Code or Codex from Terminal. Sessions and background jobs run on the server, so closing the laptop doesn't stop them and no data is copied to members' machines.

## Cost and effort

**Running costs** (DigitalOcean, [September 2026 prices](https://www.digitalocean.com/pricing/droplets)):

| Team size | Server | Encrypted storage ([$0.10/GB](https://docs.digitalocean.com/products/volumes/details/pricing/)) | Total per month |
|---|---|---|---|
| Up to ~20 members | Basic, 8 vCPU / 16 GB: $96 | 200 GB: $20 | ~$116 |
| Up to ~50 members | General Purpose, 8 vCPU / 32 GB: $252 | 500 GB: $50 | ~$302 |

Each open agent session uses 1–2 GB of memory, so size the server for how many people work at once, not headcount; it can be resized later. On top of this: the Claude or ChatGPT plans members already use, and any [optional add-ons](docs/owners-overview.md#optional-add-ons) (backups from $5/month, web search at about $0.007 per search).

**Setup for members: about 15 minutes, in one sitting.** Server owners create each account in advance and share a key through a password manager. The member pastes one command into Terminal, adds the server in their Claude or Codex app, and signs in to Google when the agent asks.

**Setup for server owners: an afternoon.** The steps are:

1. Create a DigitalOcean server with an encrypted volume, using the first-boot script in this repository.
2. Run two commands to install the software and harden the server (encrypted `/home`, SSH keys only, hidden processes between users, automatic security updates).
3. Create an internal Google OAuth app with read-only scopes and copy its file to the server.
4. Add each member with one script (about ten minutes each).

I had Claude Code do all of these steps through browser control. I stepped in only to sign in to accounts, grant access and enter payment details.

## Documents

- [Overview for server owners](docs/owners-overview.md): what gets installed, what it means for privacy, and optional add-ons.
- [Setup steps](docs/owners-setup.md): server setup, adding and removing members, maintenance.
- [Member guide](docs/member-guide.md): one-time setup and everyday use. Fill in the one placeholder, `[OWNERS_CONTACT]`, before sending it.
- [What the server can and can't do](docs/capabilities.md).
- [Instructions for members' agents](docs/member-start.md), installed as `AGENTS.md` and `CLAUDE.md` in every member's home so Claude and Codex load them automatically.

## Contents

| Path | Purpose |
|---|---|
| `workspace_import/` | The `workspace-import` command: Google sign-in, resumable imports, integrity checks, monthly refresh |
| `infra/` | First-boot script, host hardening, installer, member creation, Codex installer, scheduled jobs |
| `scripts/` | Deployment, host and member checks, metadata report for server owners |
| `config/slack-app-manifest.json` | Read-only Slack app definition, for when Slack sign-in is built |
| `tests/` | Automated tests: `uv sync --frozen && uv run pytest -q` |

Never commit credentials, exports or member data.

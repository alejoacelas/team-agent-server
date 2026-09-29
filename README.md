# Team agent server

Give each person on your team Claude Code or Codex with their entire work history at hand: every email, calendar entry and Drive file, on a server your organisation controls.

> Go through all my client calls and emails from the last two years. What questions do clients ask most often, and how have my answers changed?

## For members

- **Ask questions across everything at once.** Claude's and ChatGPT's connectors fetch a few emails or documents per request. Here the agent has the whole history as files, so it can read and classify thousands of items in one go.
- **Set up in about 15 minutes.** The server owners create the account in advance. The member pastes one command into Terminal, adds the server in the Claude or Codex app they already use, and signs in to Google.
- **Close the laptop and the work continues.** The agent runs on the server, so long analyses finish in the background and report back later.

## For server owners

- **The data stays under your control.** It lives on one server you own, not on members' laptops. Access to Google is read-only, members can't see each other's data, and anything deleted at the source is gone from the server after the next monthly refresh. Offboarding someone takes minutes.
- **It costs about $6 per member per month** when the server is full, on top of the Claude or ChatGPT plans members already have ([DigitalOcean prices](https://www.digitalocean.com/pricing/droplets), September 2026):

  | Team size | Server and encrypted storage | Per month |
  |---|---|---|
  | Up to ~20 | 8 vCPU / 16 GB, 200 GB | ~$116 |
  | Up to ~50 | 8 vCPU / 32 GB, 500 GB | ~$302 |

- **Setup takes an afternoon:**
  1. Create a DigitalOcean server with an encrypted volume.
  2. Run two commands to install the software and lock the server down.
  3. Create a read-only Google sign-in app for your organisation.
  4. Add each member with one script, about ten minutes each.

  I had Claude Code do all of this through browser control. I stepped in only to sign in to accounts, grant access and enter payment details.

- **Add only what you need.** Backups, web and LinkedIn search, Salesforce and Airtable are [optional add-ons](docs/owners-overview.md#optional-add-ons).

## How it works

Each member has a Linux account on a DigitalOcean server, with their home on an encrypted volume. A monthly job downloads their Gmail, Calendar, Tasks and Drive through a read-only Google app, replaces the previous copy and checks every file against recorded hashes. Members connect over SSH with a key the owners share through a password manager. Instructions installed in each home tell the agent where the data is and how to use the import command. Administrators can read every member's data, as on any server they run.

A one-member pilot in September 2026 tested the Google imports, the monthly refresh, the server hardening and the Google sign-in.

## Documents

- [Overview for server owners](docs/owners-overview.md): what gets installed, privacy trade-offs, add-ons.
- [Setup steps](docs/owners-setup.md): building the server, adding and removing members, maintenance.
- [Member guide](docs/member-guide.md): setup and everyday use. Replace `[OWNERS_CONTACT]` before sending it.
- [What it can and can't do](docs/capabilities.md).
- [Instructions for members' agents](docs/member-start.md).

The code is in `workspace_import/` (the import command), `infra/` (server setup) and `scripts/` (deployment and checks). Run the tests with `uv sync --frozen && uv run pytest -q`. Never commit credentials or member data.

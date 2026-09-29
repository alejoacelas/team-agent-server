# Team agent server: overview for server owners

## What it is

A private server where each member has a Linux account holding a read-only copy of their work data as ordinary files: their Gmail, Calendar, Tasks and Drive, plus shared folders they can open. Members ask Claude Code or Codex to run analyses across that full history, for example classifying hundreds of client calls and comparing the result against what those clients are doing now. The agent runs on the server through the Claude or Codex desktop app, or from Terminal on the member's Mac over SSH. Data refreshes monthly on its own.

The server owners build the server, create member accounts and hold the credentials. Members never get administrator access. Follow the [setup steps](owners-setup.md); adding each member then takes about ten minutes.

**What was tested.** A one-member pilot on DigitalOcean in September 2026 passed the Gmail, Calendar, Tasks and Drive imports (2,534 Drive items), including a folder shared by someone else, and the monthly refresh. The host hardening passed on the pilot server, including after a reboot. The paste-back Google sign-in worked live with a Workspace account. Among the add-ons, the backup job was tested against a local target rather than Spaces, web search worked with a test key, and the Airtable importer downloaded a test base completely (75 of 75 records). **Untested:** shared drives, Salesforce (automated tests only), and backups to Spaces. Slack imports worked with an existing app's token, but members can't yet connect Slack themselves.

## The default install

The [setup steps](owners-setup.md) install this and nothing else.

### Hosting

- **DigitalOcean, in the region closest to your team.** DigitalOcean's [data processing agreement](https://www.digitalocean.com/legal/data-processing-agreement) is part of its terms.
- **One shared server, one Linux account per member.** Members can't read each other's files or see each other's processes. Separate servers per member would also isolate members from each other's administrators, but multiply maintenance.
- **Size for concurrent use.** Each open agent session uses 1–2 GB of memory, alongside large downloads. The [README](../README.md#for-server-owners) gives sizes and prices; the server can be resized later.

### Data

DigitalOcean [doesn't encrypt Droplet disks](https://www.digitalocean.com/security/shared-responsibility-model-droplets) but [does encrypt volumes](https://docs.digitalocean.com/products/volumes/details/features/).

- **Member homes live on an encrypted volume at `/home`; `/tmp` is held in memory.** Member data never touches the unencrypted disk. Without the volume attached, the server won't boot normally.
- **Each refresh replaces the previous copy.** Anything deleted at the source leaves the server with the next monthly refresh. A refresh that returns far fewer records than last time stops instead of replacing the good copy.
- **Members can delete their own data.** Their agent can delete downloaded copies and stop a source downloading them again.
- **No backups.** Downloaded data can be fetched again. Members' own notes and analyses in `~/workspace/work` are lost if the server is lost, unless you add [backups](#optional-add-ons).

### Access

- **SSH with keys only; port 22 open to the internet.** Root login is off, and only the workspace groups can log in. An IP allow-list would lock out travelling members.
- **Server owners generate each member's key and share it through a password manager.** Members then finish setup in one sitting. The owners briefly hold the key, but administrators can already read everything.
- **Administrators can read every member's data and saved credentials.** Linux account separation doesn't hide anything from `root`, and the monthly refresh must run unattended, so members' Google tokens sit on the server.

### Sources

- **Google: an Internal OAuth app in your Google Cloud organisation, with read-only scopes.** Each member approves access for their own account. There's no domain-wide delegation, which would expose every mailbox. If your Workspace API controls restrict third-party apps, mark this app as Trusted.
- **Shared folders follow Drive sharing.** Members download a shared folder by giving their agent its link; their own Drive access decides what they can download.
- **Google Takeout and other archives.** Members can upload an archive to `~/workspace/incoming` and import it.

### AI agents

- **Members use Claude Code or Codex with your organisation's Claude or ChatGPT plan.** Whatever the agent reads is sent to Anthropic or OpenAI under that plan's terms. Members' personal connectors in those accounts also work in server sessions.
- **Members use Auto permission mode**, which screens the agent's actions for risk. Access to every source is read-only.

### Operations

- **Security updates install nightly, with an automatic reboot at 04:00 server time when needed.** Open agent sessions end then; background jobs do too, and resume on request.

## Optional add-ons

Each is a section in the [setup steps](owners-setup.md#optional-add-ons).

1. **Backups of members' work (about $5/month).** Nightly encrypted copies of each member's work folder in DigitalOcean Spaces, encrypted on the server before upload. Default retention is 7 daily plus 4 weekly copies, about five weeks. Downloaded data and credentials are left out.
2. **Deleting notes built from deleted data.** Members' notes can quote records that are later deleted at the source, and nothing links a note to the records it used. If this matters to you, make it the member's job to delete such notes, and the server owners' job to purge them from backups on request.
3. **Codex.** Install it if any member uses the Codex app or Codex in Terminal. The Claude app installs itself.
4. **Web and LinkedIn search through [Exa](https://exa.ai)** (about $0.007 per search). One API key for the server. Built-in web search can't read LinkedIn profiles; Exa can. Set a spending limit on the key.
5. **Salesforce and Airtable.** One read-only integration credential per system, so its permissions decide what every member with it can see.
6. **Slack (not built yet).** A read-only Slack app is defined in `config/`, covering channels and private channels the member belongs to, but not direct messages. The member sign-in command doesn't exist yet.

## If you're concerned about…

- **Members' agents skipping safety checks:** block Bypass permissions mode for your organisation's Claude accounts by setting `permissions.disableBypassPermissionsMode` to `"disable"` in [managed settings](https://code.claude.com/docs/en/settings).
- **Which shared data each member may see:** decide it in Drive sharing and in the integration credential's permissions, before members connect those sources.

## What this means in practice

- **Where member data exists:** on the encrypted volume, with Anthropic or OpenAI for whatever the agent reads, and in backups if you add them (work folders only).
- **Members keep their work by saving it in `~/workspace/work`.** Everything under `~/workspace/data` is replaced by refreshes.
- **Member offboarding** takes minutes: revoke Google access, then delete the account.
- **Ongoing work:** a monthly check of the metadata report and disk space, plus a Codex update if you installed it.
- **Not included:** Google Form responses, Drive comments and version history, and browser automation. See [what the server can and can't do](capabilities.md).

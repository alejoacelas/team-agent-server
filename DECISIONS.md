# Decisions

## Core decisions

### Keep the install small and legible

- [The default install is minimal; everything else is an optional add-on.](#minimal-default)
- [Examples stay generic.](#generic-examples)

### Deletions at the source reach the server

- [Each published refresh deletes the previous copy.](#refresh-replaces)
- [Members delete their own downloaded data.](#member-deletion)

## Details

### Minimal default

The default install is Google (Gmail, Calendar, Tasks, Drive), shared folders, archive uploads, the encrypted volume and per-member accounts. Backups, Codex, web search, Salesforce, Airtable, Slack and handling of notes derived from deleted data are optional add-ons. Concerns such as bypass-permissions mode get a one-line "if you're concerned about…" note instead of a default. Reason: owners of small organisations should be able to read what they are installing in one sitting and add only what they need. Backups stay off until `/etc/workspace/backup.env` exists and the timer is enabled.

### Generic examples

The project was built for a team that analyses call transcripts. Public docs use client-call examples and "members", so the origin isn't identifiable.

### Refresh replaces

`Snapshot.finish(publish=True)` removes every other run of that source after switching `current`. This replaced keeping all old runs, so deletions propagate within one monthly refresh without anyone reviewing retention. The record-count drop check still stops a refresh that would replace a good copy with a much smaller one.

### Member deletion

Everything under a member's `~/workspace/data` belongs to that member, so their agent can delete it and turn the source off. Server owners are needed only to purge backups.

## Decision log

- 2026-09-29: Created as a public, organisation-neutral version of a private pilot, with the choices above.

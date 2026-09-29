# Team agent server

Scope: the installable code and documentation for a server that gives each team member a read-only copy of their work data for Claude Code or Codex (DigitalOcean, one Linux account per member, read-only imports from Google and optional sources). This repository is public: keep it free of any organisation's names, links, people or infrastructure details.

Keep `README.md`, `docs/owners-overview.md`, `docs/owners-setup.md`, `docs/member-guide.md`, `docs/capabilities.md` and `docs/member-start.md` consistent with the code and with each other. When behaviour changes, update the claim and say whether it was tested on a real server. Member-facing text uses plain language and "If X, then Y" instructions.

The default install stays minimal. New features go under "Optional add-ons" in the overview and setup steps unless every team needs them.

Run `uv run pytest -q` before committing. Never commit credentials, exports, member data, server addresses or host keys.

Call the people who run the server "server owners" and everyone else "members". Example prompts use client-call scenarios.

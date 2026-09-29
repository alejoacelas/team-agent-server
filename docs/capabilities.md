# What the workspace can and can't do

## What it can do

1. **Hold your full history in one place.** Your Gmail (everything except Spam and Trash), Calendar, Tasks and Drive, plus shared folders you can open, and Salesforce or Airtable if the server owners connected them. Example: "Which recommendations have I made to clients most often, and did they act on them?"
2. **Analyse hundreds of records at once.** Example: "How has the mix of topics in my client calls shifted this year? Ask me questions to clarify first."
3. **Run long jobs without you.** Example: "Summarise all my call notes in the background and let me know when it's done."
4. **Keep your notes next to the data.** Analyses, scripts and notes saved in your work folder stay there across refreshes.
5. **Stay up to date.** Everything refreshes monthly on its own, and the agent can refresh any source on request.
6. **Use your usual connectors.** The connectors in your Claude or ChatGPT account keep working in workspace sessions.
7. **Look people up on the web and LinkedIn, if the server owners added web search.** Example: "What are the clients I worked with last year doing now?"

## Rules

1. **Save your work in `~/workspace/work`.** Anything saved under `~/workspace/data` is replaced at the next refresh.
2. **The workspace only reads your accounts.** It can't send email, accept invitations, or edit Drive, Salesforce or Airtable. Edits to downloaded copies stay on the server.
3. **Only sessions connected to the workspace can see your data.** That means a desktop app session on **Team workspace**, or Claude Code or Codex in Terminal after "Open my team workspace". The Claude website, the mobile apps and "Local" or "Cloud" sessions can't.
4. **There's no browser on the server.** The agent can't click through websites, fill in forms or use your logged-in accounts.
5. **Chats end when you close the app.** Background jobs keep running.
6. **Other members can't see your data. The server owners can.**
7. **Slack isn't available yet.**
8. **Not included:** Google Form responses, Drive comments, older versions of documents.

## Implementation details

- **Gmail:** each refresh re-lists the whole mailbox rather than fetching changes since the last run. Large mailboxes take longer, but nothing is missed if a refresh fails partway.
- **Drive:** native Google files are exported (Docs as structured JSON plus text; Sheets and Slides as XLSX and PPTX plus text; Forms as their definition). A file type the exporter doesn't support fails the run visibly instead of being skipped. Shortcuts are listed but not followed. A folder shared by another person was tested; shared drives are listed through that drive's own index but haven't been tested.
- **Salesforce and Airtable:** records are saved as JSON through read-only credentials. Attachments aren't downloaded. Airtable was tested on a test base (75 of 75 records); Salesforce has automated tests only.
- **Web and LinkedIn:** `workspace-import web-search` and `web-contents` use Exa. Plain fetches of LinkedIn are blocked; Exa returns profile text.
- **Safety checks:** if a source suddenly returns far fewer records than last time, the refresh stops rather than replacing the good copy.
- **Interrupted downloads** resume from their checkpoint. Every completed copy is checked against recorded file hashes (`workspace-import verify SOURCE`).
- **Old copies:** each completed refresh deletes the previous copy, so data deleted at the source leaves the server with the next refresh.
- **Tools on the server:** Python 3, `ripgrep`, `jq`, `sqlite3`, `git` and `poppler-utils` (PDF text). If Codex is installed, `codex exec` runs model calls in background jobs. Members can't install system packages, but can install Python packages in a virtual environment in their home.
- **Disk:** there are no per-member quotas; the server owners watch overall usage.

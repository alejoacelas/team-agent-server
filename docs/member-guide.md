# Your team workspace

Your team workspace is a private server holding your work history as ordinary files that Claude Code and Codex can read directly: your Gmail, Calendar, Tasks and Drive, plus shared folders you can open. Because the agent reads everything at once, you can ask for analyses across hundreds of calls and emails, not only answers about one person. Your own Claude or ChatGPT connectors keep working.

Things you can ask:

> Go through all my client calls and emails from the last two years. What questions do clients ask most often, and how have my answers changed? Show me a few examples, and ask me questions to clarify before you start.

> Which resources do I recommend most in my follow-up emails, and has that changed over time?

> Find clients who came back for a second project and tell me what changed between the two.

Setup takes about 15 minutes; the server owners have already created your account. You need a Mac and one of: the Claude desktop app, the Codex app, or Claude Code or Codex in Terminal. Sign in with your organisation's Claude or ChatGPT account, not a personal one: whatever the agent reads is sent to that provider.

## Part 1: One-time setup

### Step 1. Install your key

1. In your password manager, open the item **Team workspace – [your name]** that the server owners shared with you.
2. Download the attached file `team-agent-server` to your **Downloads** folder. Keep its name exactly as it is.
3. Open **Terminal** (press ⌘-Space, type `Terminal`, press Return).
4. Copy the item's **Setup command** field. Paste it into Terminal and press Return.

- **If you see `Setup complete. Your workspace folder is /home/…`:** go to step 2. If you use Codex, note the folder path.
- **If you see `Host key verification failed`:** don't try to fix it. Contact `[OWNERS_CONTACT]`.
- **If you see anything else:** take a screenshot of Terminal and ask Claude or ChatGPT what went wrong and how to fix it. If that doesn't solve it, send the screenshot to `[OWNERS_CONTACT]`.

The key file gives access to your data. Don't copy it anywhere else or send it to anyone.

### Step 2. Connect your app

**Claude desktop app**

1. Open the **Code** tab.
2. Click the environment menu next to the message box (it usually says **Local**) and choose **+ Add SSH connection**.
3. Enter the name `Team workspace` and the SSH host `team-agent-server`. Leave Port and Identity File empty.
4. Save. The first connection takes a minute while Claude installs itself on the server.

**Codex app**

1. Open **Settings → Connections**, find `team-agent-server` and turn it on.
2. Create a project on that connection, using the workspace folder path from step 1.

**Claude Code or Codex in Terminal**

Nothing to set up here; step 3 explains how to start.

### Step 3. Start your first session and connect Google

**If you use a desktop app:**

1. Start a new session. **Check that it is running on the workspace.** In Claude, the environment menu must say **Team workspace**. In Codex, the project must be the one on `team-agent-server`.
2. Paste this message:

> Check my team workspace, connect my Google account, then download my Gmail, Calendar, Tasks and Drive. Tell me what's available when you're done.

**If you use Terminal:**

1. Open Terminal and run `claude` or `codex`.
2. Paste this message. It also teaches your agent a phrase for later sessions:

> Save this instruction in your global instructions file for me (~/.claude/CLAUDE.md for Claude Code, ~/.codex/AGENTS.md for Codex): "When I say 'open my team workspace', run commands on my team workspace with `ssh team-agent-server`, read ~/AGENTS.md there and follow it. Files there are on the server, not this Mac." Then open my team workspace: check it, connect my Google account, and download my Gmail, Calendar, Tasks and Drive.

When the agent asks to run `ssh team-agent-server …` commands, approve them. In later sessions, just say **"Open my team workspace"**.

**Then, in either case:**

1. **Before you open the link, know what comes next:** after you approve, your browser shows an error page, **"This site can't be reached. 127.0.0.1 refused to connect."** (Safari says "Safari Can't Connect to the Server"). That's expected: the address of that error page is what the agent needs.
2. Open the Google link the agent gives you, choose your **work** Google account and click **Continue**.
3. On the error page, click the address bar, copy the **entire** address (it starts with `http://127.0.0.1:8765/`) and paste it into the chat.
4. The agent confirms Google is connected and starts downloading. A large Drive can take several hours the first time. Downloads keep running on the server after you close the app; in a later session, ask "Are my downloads finished?"

To add shared data, give the agent a link, for example "Also download the client call transcripts folder: [link]".

## Part 2: Rules to know

1. **Save anything you want to keep in `~/workspace/work`.** Everything in `~/workspace/data` is replaced by the monthly refresh. Your work folder is never touched by refreshes.
2. **Run long analyses in the background.** Ask the agent to run them "in the background". They keep going after you close the app, and you can check on them later.
3. **Use the Auto permission mode.** In Claude, choose **Auto** in the mode menu next to the message box (in Terminal, press Shift-Tab until it shows auto mode). In Codex, keep the default, **Auto**; it asks before commands that use the internet, and you can approve the ones that run `workspace-import`. If Auto mode restrictions keep interrupting your AI, ask the server owners before switching to **Bypass permissions** or **Full access**.
4. **Paste only the Google address from step 3 into the chat.** Never paste passwords, codes you didn't expect, or the contents of `~/.ssh`.
5. **If you lose your Mac, tell the server owners the same day.** On a new Mac, ask them for a new key rather than copying the old file.
6. **To delete downloaded data, ask your agent** to delete it and to stop that source downloading it again.

## If something goes wrong

First, ask your agent what went wrong and how to fix it. If the agent can't reach the workspace, ask Claude or ChatGPT instead, with a screenshot of the error.

| If… | Then… |
|---|---|
| In a desktop app, the agent can't find your files or offers to "SSH into the server" | The session is running on your Mac or in the cloud, not on the workspace. Start a new session and pick **Team workspace** (Claude) or the `team-agent-server` project (Codex). Sessions can't be moved between environments. |
| In Terminal, the agent doesn't know what "open my team workspace" means | The saved instruction is missing. Paste the Terminal message from step 3 again. |
| The app shows `Permission denied (publickey)` | The key file or setup command doesn't match your account. Contact `[OWNERS_CONTACT]`. |
| The app shows `Host key verification failed` or says the server's identity has changed | **Stop.** Don't accept or delete anything. Contact `[OWNERS_CONTACT]`: this protects you from connecting to an impostor server. |
| Google says **"Access blocked"** or the agent says the account doesn't match | You chose a personal Google account. Ask the agent to start the Google connection again and pick your work account. |
| The agent says the sign-in expired or didn't match | The link lasts 15 minutes and works once. Ask the agent to start again, and copy the whole address from the address bar. |
| The agent says a download failed or was interrupted | Say "Resume the interrupted download". It continues where it stopped. |
| The agent says something needs the server owners | Forward its message to `[OWNERS_CONTACT]`. |
| The session suddenly disconnects at night | The server restarts at 04:00 when security updates need it. Start a new session. |

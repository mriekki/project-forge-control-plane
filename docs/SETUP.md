# Project Forge Builder Setup

This page is for a developer who has received a **Project Forge** invitation.

You do **not** configure the Control Plane, GitHub Actions secrets, Bootstrap, or Project Forge infrastructure. The invitation issue is your onboarding portal.

> **Privacy:** Control Plane invitation issues are public. Never paste source code, Project requirements, credentials, tokens, private keys, or other private information into them.

## Activate Project Forge

### 1. Open your invitation issue

Confirm the issue names your exact **GitHub username**.

If the username is wrong, stop and ask the Project Forge admin for a fresh invitation.

### 2. Install Project Forge Builder

Use the **Project Forge Builder** GitHub App link in the invitation issue and install/approve it for your GitHub account if needed.

- **Recommended — least privilege:** select only the repositories Project Forge should operate on. Add each future Project repository to the App installation before generation or update operations need it.
- **Convenience option:** allow the App for all repositories in your GitHub account if you prefer not to manage repository selection as Projects are created.

Project Forge workflows still mint short-lived tokens scoped to the exact repository required by each operation. Selecting repositories additionally narrows the App installation itself.

If the App is already installed, do not remove or reinstall it just to continue.

If you have no repository to select yet, create a private starter repository under your own GitHub username (leave it empty if it will be your first generated Project). Then select it in the App installation. In GitHub, **Settings → Applications → Installed GitHub Apps → Project Forge Builder → Configure** is where you can add future repositories. Keep the App installed on your own account; you do not need access to private platform repositories.

### 3. Accept the invitation

While signed in as the GitHub user named in the invitation, add a new comment containing exactly:

```text
/accept-project-forge
```

Project Forge automatically checks:

```text
GitHub identity
→ GitHub App installation
→ developer authorization
→ public Project Forge operating contract
→ READY FOR PROJECT FORGE
```

When the issue reports **Project Forge is ready**, GitHub onboarding is complete and the issue closes automatically.

## Configure ChatGPT once

The Project Forge Builder GitHub App authorizes Control Plane automation. It is separate from ChatGPT's GitHub connection, which lets ChatGPT inspect and, where supported, work with repositories as you. Connect your own GitHub account in ChatGPT and verify access to the intended Project repository. If the available connection cannot perform the required writes, use the supported manual/VS Code handoff; do not share a token or another Builder's credentials.

Follow the public one-time setup guide:

https://github.com/mriekki/project-forge-platform/blob/main/chatgpt/SETUP.md

If you prefer guided copy-and-paste setup, open a new ChatGPT conversation and use this prompt:

```text
Help me set up Project Forge as a Builder. Read the current public descriptor at https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json, verify its complete pinned immutable contract snapshot, and use the canonical ChatGPT setup guide. Ask for my GitHub username and any useful personal environment preferences that are missing. Give me the exact canonical Project instructions and a minimal valid Developer Profile to copy into my ChatGPT Project. Do not guess missing details, rewrite the canonical instructions, or add secrets or Project state. Explain how to connect my own GitHub account and verify the intended repository access. Do not generate a Project yet.
```

If verification cannot be completed, stop rather than copying remembered instructions. Use the guide above as the authoritative manual fallback. After copying the instructions into your ChatGPT Project, start a chat there and say `Verify my Project Forge setup.`

Every Builder uses the same canonical Project Forge Project instruction. Personal GitHub/workstation/learning preferences belong only in that Builder's small Developer Profile.

Do **not** copy product requirements, component SHAs, current Project state, or legacy handoff contents into Project instructions.

Then start with:

```text
New Project
```

## Your first Project

For a newly generated Project, use a private empty repository under your own GitHub username. Do not use a repository name starting with `project-forge-` (reserved). Do not initialize the target with a README, license or gitignore. Grant Project Forge Builder access to that repository and verify the ChatGPT connection can reach it. The guided discovery confirms the exact target before generation. After generation and baseline CI, clone the repository, open its generated VS Code workspace, and run `/setup`. Choose local development first if you do not yet have a deployment target. No access to someone else's server or household is required.

## Recovery

### App installation not verified

Use the direct **Project Forge Builder** link posted on the invitation issue, approve the App for the invited GitHub user, then add a fresh comment containing exactly:

```text
/accept-project-forge
```

### Invitation expired

Ask the Project Forge admin for a fresh invitation. Expiration applies only while an invitation is still pending. A closed or declined invitation must not be reused or reopened to renew it. If you have more than one open invitation, use the earlier valid invitation or ask the admin to reconcile them.

### Builder is already ACTIVE but readiness needs checking

On the original invitation issue, comment:

```text
/project-forge-doctor
```

If the original invitation issue is unavailable, open a fresh empty-body issue titled:

```text
[project-forge-doctor] <github-user>
```

A successful readiness retry closes its issue.

### Decline a still-pending invitation

While signed in as the invited GitHub user, comment:

```text
/decline-project-forge
```

An already-ACTIVE Builder cannot decline the completed invitation; an admin must use the revocation flow to remove future authorization.

## More about Project Forge

- Overview: https://github.com/mriekki/project-forge-platform/blob/main/WELCOME.md
- ChatGPT setup: https://github.com/mriekki/project-forge-platform/blob/main/chatgpt/SETUP.md
- Control Plane: https://github.com/mriekki/project-forge-control-plane

Administrators/operators: see [`ADMIN_SETUP.md`](ADMIN_SETUP.md).
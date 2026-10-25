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

- **Simplest:** allow the App for all repositories in your GitHub account.
- **Tighter access:** select repositories. If you do this, each future Project repository must be added before Project Forge can operate on it.

If the App is already installed, do not remove or reinstall it just to continue.

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

Follow the public one-time setup guide:

https://github.com/mriekki/project-forge-platform/blob/main/chatgpt/SETUP.md

Every Builder uses the same canonical Project Forge Project instruction. Personal GitHub/workstation/learning preferences belong only in that Builder's small Developer Profile.

Do **not** copy product requirements, component SHAs, current Project state, or legacy handoff contents into Project instructions.

Then start with:

```text
New Project: <your idea>
```

## Recovery

### App installation not verified

Use the direct **Project Forge Builder** link posted on the invitation issue, approve the App for the invited GitHub user, then add a fresh comment containing exactly:

```text
/accept-project-forge
```

### Invitation expired

Ask the Project Forge admin for a fresh invitation. Expiration applies only while an invitation is still pending.

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
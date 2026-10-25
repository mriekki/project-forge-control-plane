# Project Forge Control Plane — Administrator Setup

> **For Project Forge administrators/operators only.** Project Builders do not need to configure this repository, GitHub Actions variables/secrets, or the GitHub App. Builder onboarding is intentionally kept separate in [`SETUP.md`](SETUP.md).

This repository is the public orchestration surface for Project Forge generation, Builder invitation/authorization, and supported remote update workflows. Private foundational source topology stays behind protected Actions configuration; the public `@mriekki/project-forge` package remains the normal reusable-asset delivery boundary for generated Projects.

Canonical repository identity:

```text
mriekki/project-forge-control-plane
```

The canonical generation manifest is `PROJECT_BOOTSTRAP.json`.

## Security boundary

Public operational issues contain only safe identities:

```text
[invite-project-forge] github-owner
[test-invite-forge]
[project-forge-doctor] github-owner
[revoke-project-forge] github-owner
[generate-project] owner/repository
[sync-core] owner/repository
```

Issue bodies must remain empty. Private Project definitions, baseline contents, source code, foundational repository topology, credentials, and secrets never belong in a Control Plane issue.

Private generation data stays in the target repository's `PROJECT_BOOTSTRAP.json`. Workflows read target-private files only after minting a GitHub App installation token scoped to that exact repository.

Do not store PATs or npm publish tokens in this repository. The credential model is one GitHub App private key plus protected source-repository mappings stored as Actions secrets; workflows mint short-lived installation tokens for the exact source/target repositories needed by each operation.

## GitHub App registration

Create one GitHub App owned by the Control Plane owner and configure it so it can be installed on approved Builder accounts.

Public display identity:

```text
GitHub App name: Project Forge Builder
```

Keep GitHub's identity terms distinct:

- **App name** is the human-facing registration name: `Project Forge Builder`.
- **App slug** is GitHub's URL-safe App identifier and may retain historical wording after a display-name change.
- **GitHub App bot username** is `<app-slug>[bot]`.
- **App installation** is the App's authorization on an owner/account and selected repositories.

Workflows resolve the actual App slug/bot identity rather than guessing it. A display-name rename must not be coupled to a bot-identity or credential migration unless GitHub itself changes those values.

Required repository permissions for generation plus the existing remote Core-sync workflow:

- **Contents: Read and write**;
- **Workflows: Read and write**;
- **Pull requests: Read and write**;
- **Checks: Read-only**;
- **Metadata: Read-only**.

The Control Plane does not need target-repository Issues permission. It comments on its own public issues using the workflow run's normal `GITHUB_TOKEN`.

The App does not need webhooks for this design; onboarding, generation, and Core sync are initiated by this repository's issue-triggered Actions workflows.

When permissions are expanded on an existing App installation, GitHub may require the installation owner to approve the change. Confirm the installation remains active before relying on the new permission.

## Installations

Install **Project Forge Builder** on the Control Plane owner account and on each approved Builder account.

- **Recommended — least privilege:** select only repositories that Project Forge should operate on. Add a newly created Project repository to the installation before generation or update operations need it.
- **Convenience option:** allow all repositories when the Builder explicitly prefers not to manage repository selection as Projects are created.

Each workflow still mints a short-lived installation token scoped to the exact repository required by that run. Selected-repository installation provides an additional outer authorization boundary and reduces the App installation's standing scope.

The invitation workflow derives the public installation URL from the App slug returned by `actions/create-github-app-token`; no separately maintained installation-link setting is required.

## Actions configuration

Configure these values in **Settings → Secrets and variables → Actions**:

1. Store the App **Client ID** as Actions variable `APP_CLIENT_ID`.
2. Store the complete App private key as Actions secret `APP_PRIVATE_KEY`.
3. Store the exact private Bootstrap source as Actions secret `BOOTSTRAP_SOURCE_REPOSITORY` using `owner/repository` format.
4. Store the exact private Core source as Actions secret `CORE_SOURCE_REPOSITORY` using `owner/repository` format.
5. Do not commit the protected source mappings or credentials into this public repository.
6. Keep `config/developers.json`, `config/invitation-policy.json`, and `config/allowed-owners.json` valid under CI.

The generation and Core-sync workflows validate these protected mappings, mask the resolved private repository identities in logs, and fail closed if required configuration is absent or malformed. Public contract compatibility still pins exact accepted revisions; the protected mapping only supplies the private repository location.

The invitation workflow uses the App credentials to resolve GitHub's actual App slug and constructs the standard GitHub App installation URL automatically. Renaming the App display name does not require rotating `APP_CLIENT_ID` or `APP_PRIVATE_KEY`.

## Developer invitation contract

Normal onboarding uses the invitation workflow; do not manually add a normal Builder to `config/allowed-owners.json`.

An ACTIVE admin creates one empty-body issue:

```text
[invite-project-forge] github-owner
```

The invited Builder follows the concise instructions in the invitation issue and [`SETUP.md`](SETUP.md): install/approve **Project Forge Builder** if needed, then comment exactly `/accept-project-forge` in the invitation issue.

The claim workflow verifies identity, invitation lifetime, and Project Forge Builder App installation before updating the developer registry and authorization projection.

The invited owner can decline with `/decline-project-forge`. Unclaimed invitations expire after the configured claim window.

Successful activation automatically verifies the public Project Forge ChatGPT contract. That readiness verification includes the complete immutable contract snapshot plus the canonical Control Plane identity and exact privacy-safe generation tuple: Bootstrap revision/protocol/catalog, public package/version, and profile. `/project-forge-doctor` remains the retry/diagnostic path if readiness later needs attention.

## Admin onboarding self-test

Choose **Issues → New issue → Test Project Forge onboarding** and submit the prefilled empty-body issue:

```text
[test-invite-forge]
```

The workflow infers the target from the active admin who opened the issue. It cannot target another user and never mutates authorization state. Continue by adding `/accept-project-forge` to that same test issue when instructed.

## Per-Project generation request contract

After discovery and Project Definition approval:

1. the Builder owns a private, safe target repository;
2. ChatGPT verifies exact GitHub owner/target safety;
3. only the approved `PROJECT_BOOTSTRAP.json` seed is written before generation;
4. the manifest pins exact Bootstrap revision compatibility and an exact `@mriekki/project-forge` package/version/profile;
5. ChatGPT opens an empty-body public issue here titled `[generate-project] owner/repository`;
6. the author must equal the target owner and be ACTIVE with generation authorization;
7. the workflow resolves the protected Bootstrap source mapping and obtains a source-only token plus an exact-target token;
8. the checked-out source revision is verified against the public accepted generation revision before the private manifest is validated;
9. the workflow downloads/verifies exactly the approved package;
10. deterministic generation runs through the canonical generation path;
11. generated tools/baselines are verified before publication;
12. the validated generated tree is published without force-pushing; and
13. target default-branch CI is verified before local setup acceptance.

Normal approved discovery may use `integrity: "registry"` for deterministic machine resolution. Humans are not expected to discover or paste npm integrity metadata. Package/version/profile are the meaningful human approval surface; the generation boundary resolves and verifies exact integrity before reusable mutation.

Missing protected source configuration, missing access, unavailable exact packages, integrity mismatch, invalid provenance, managed-path conflict, or failed generation are stop conditions. They never authorize silent fallback to a different package, source revision, local ZIP, destination, or component revision.

## Remote Core-sync compatibility path

A supported consumer may request:

```text
[sync-core] owner/repository
```

with an empty body. The workflow resolves the accepted Core source from `CORE_SOURCE_REPOSITORY`, validates authorization and baseline integrity, uses exact source/target tokens, creates a new non-force branch when needed, opens a consumer PR, and reports success only when its checks are green. Merge remains a human decision.

## Repository identity boundary

The public Control Plane and public Platform identities may appear in public documentation because they are intended public surfaces. Private foundational source repository identities belong only in protected Actions configuration. Historical public Git data is not rewritten; this boundary governs active current files and future contract revisions.

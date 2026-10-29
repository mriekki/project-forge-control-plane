# Project Forge Developer Invitations

The Control Plane invitation system answers one question: **who is authorized to use Project Forge automation?**

It is intentionally separate from the public ChatGPT operating contract and from each generated Project repository.

```text
Invitation / developer registry
Who may use Project Forge?

Public ChatGPT contract
How should ChatGPT guide the Builder now?

Generated Project repository
What is true about this Project?
```

## Builder-facing happy path

An ACTIVE Project Forge admin opens **Issues → New issue → Invite a Project Forge Builder** and enters the developer's exact GitHub username.

The issue is initially submitted with the machine trigger:

```text
[invite-project-forge] <github-user>
```

The issue body must be empty at submission. That preserves the public-input safety boundary: the admin supplies only the GitHub identity, with no Project details, credentials, or other free-form invitation state.

Before publishing the invitation instructions, the Control Plane verifies:

- the issue was opened by an ACTIVE admin with `invite-developer`;
- the body is empty;
- the target uses valid GitHub-login syntax;
- the target exists on GitHub;
- the target is a GitHub **user**, not an organization;
- the target is not already ACTIVE.

After those checks pass, the workflow persists a small hidden machine-readable onboarding marker in the issue body and changes the visible title to:

```text
You're invited to Project Forge
```

The persisted marker contains only the already-validated public GitHub identity and invitation kind. It is workflow-written and rendered as an HTML comment, so the visible issue and GitHub notification subject remain human-facing. Acceptance, decline, doctor retry, and expiry logic resolve the invitation from this persisted state rather than depending on the visible title.

The invitation issue then gives the Builder only two required actions:

```text
1. Install/approve Project Forge Builder.
2. Comment exactly: /accept-project-forge
```

The issue itself is the onboarding portal. A forwarded issue URL does not grant authorization.

## Claim validation

A claim is valid only when all of these are true:

- the invitation is still pending;
- the persisted onboarding state resolves a valid invited GitHub user;
- the original inviter remains authorized;
- the claim is within `config/invitation-policy.json`;
- the commenter exactly matches the invited GitHub user;
- the comment is exactly `/accept-project-forge` after harmless surrounding whitespace is removed;
- Project Forge can verify the GitHub App installation for that user.

Only then may the Control Plane persist the developer as ACTIVE.

Registry writes are serialized by the `project-forge-developer-registry` concurrency group. They use normal Git fast-forward/rebase mechanics only; no force-push or history rewrite is allowed. A concurrent/conflicting `main` update fails safely and posts recovery guidance on the invitation issue.

## Automatic readiness

After activation is persisted, the same claim run verifies the public Project Forge ChatGPT contract using the shared runtime verifier.

Happy path:

```text
PENDING
→ identity verified
→ App verified
→ ACTIVE
→ public contract verified
→ READY FOR PROJECT FORGE
→ invitation issue CLOSED
```

If authorization becomes ACTIVE but public-contract verification is temporarily unavailable, the invitation stays open as the recovery surface.

After the underlying problem is fixed, the Builder or an admin comments:

```text
/project-forge-doctor
```

A successful doctor retry reports **READY FOR PROJECT FORGE** and closes the issue.

An already-ACTIVE Builder without an invitation issue may instead open an empty-body issue:

```text
[project-forge-doctor] <github-user>
```

## Pending-only terminal states

Decline and expiration apply only while an invitation is still pending.

```text
PENDING → DECLINED
PENDING → EXPIRED
```

They must never describe an already-ACTIVE Builder as declined or expired.

The invited GitHub user may decline by commenting exactly:

```text
/decline-project-forge
```

Expiration uses the configured claim window and scans all open Control Plane issues rather than an arbitrary first-page limit.

Neither decline nor expiration changes developer authorization because both are permitted only before activation.

## Recovery behavior

Expected human input errors are reported on the issue, not only in the Actions log.

Examples include:

- malformed/non-empty invitation;
- unknown or non-user GitHub target;
- wrong claimant identity;
- expired invitation;
- already-ACTIVE target;
- missing GitHub App installation;
- malformed decline;
- malformed doctor request;
- safe registry persistence conflict.

The workflow remains fail-closed. Actionable issue guidance does not relax validation.

## Admin onboarding self-test

An ACTIVE admin may open **Test Project Forge onboarding** with the machine trigger:

```text
[test-invite-forge]
```

After validation, the workflow changes the visible title to:

```text
Project Forge onboarding test
```

and persists the same kind of hidden, workflow-written state marker used by real invitations. This keeps the self-test notification subject human-facing while preserving the same acceptance-path mechanics.

The zero-input self-test is self-only and non-authorizing. It verifies the current onboarding path without:

- mutating the developer registry or compatibility projection;
- changing roles/capabilities;
- creating a Project repository;
- deploying or tearing down anything.

The test uses the same current App and public-contract verification as the real onboarding path.

## Developer registry

`config/developers.json` is the operational registry.

Roles:

- `admin` — normal Project Builder capabilities plus invitation/revocation administration;
- `project-author` — normal Project Builder with generation and supported update/sync authorization.

`config/allowed-owners.json` is a generated compatibility projection of ACTIVE developers with `generate-project`. CI validates the invariant.

No secrets, credentials, private Project definitions, or repository contents belong in either file.

## Revocation

An ACTIVE admin opens an empty-body issue:

```text
[revoke-project-forge] <github-user>
```

Revocation removes **future Control Plane authorization only**. It does not delete, transfer, disable, or mutate repositories already owned by the Builder.

The last ACTIVE admin cannot be revoked.

## Public onboarding surfaces

Builder setup:

```text
https://github.com/mriekki/project-forge-control-plane/blob/main/docs/SETUP.md
```

Project Forge overview:

```text
https://github.com/mriekki/project-forge-platform/blob/main/WELCOME.md
```

One-time ChatGPT setup:

```text
https://github.com/mriekki/project-forge-platform/blob/main/chatgpt/SETUP.md
```

Low-level public contract bootstrap:

```text
https://github.com/mriekki/project-forge-platform/blob/main/chatgpt/START_HERE.md
```

New Builders do not need legacy handoff files or direct access to private Bootstrap/Core repositories.

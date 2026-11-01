# Project Forge Control Plane

Public, credential-isolated orchestration for **Project Forge** onboarding, GitHub-first Project generation, existing-repository adoption, developer authorization, and supported remote update workflows.

Canonical repository identity:

```text
mriekki/project-forge-control-plane
```

Canonical technical commands and schema identifiers include `[invite-project-forge]`, `/accept-project-forge`, `[generate-project]`, `[adopt-project]`, `PROJECT_BOOTSTRAP.json`, and `PROJECT_ADOPTION.json`.

## Admin quick start

From **Issues → New issue**, choose:

- **Invite a Project Forge Builder** — real invitation/authorization for another GitHub owner;
- **Test Project Forge onboarding** — non-authorizing self-test using your own active admin account.

The self-test is zero-input: submit the prefilled issue. The workflow infers the active admin from the issue opener, renders the prospective invitation message, and can report `TEST READY FOR PROJECT FORGE`. It never changes authorization, Projects, or deployments.

For a real invitation, use:

```text
[invite-project-forge] github-owner
```

The invitation issue is the onboarding portal. The invited GitHub identity:

1. opens the invitation;
2. installs/approves the **Project Forge Builder** GitHub App if needed; and
3. replies in that same issue with exactly `/accept-project-forge`.

The workflow verifies the exact identity and GitHub App installation before activation. The invited owner may use `/decline-project-forge`; unclaimed invitations expire under `config/invitation-policy.json`.

Builder-facing setup is intentionally concise in `docs/SETUP.md`. Administrator/operator configuration is separate in `docs/ADMIN_SETUP.md`. See `docs/INVITATIONS.md` for the complete real/test invitation lifecycle.

## Ownership model

Reusable Project Forge capabilities are separately owned behind the public Platform and Control Plane boundaries. Public repositories describe capability ownership and compatibility, but do not need to disclose the names of private foundational source repositories.

- the public **Project Forge Platform** owns the `@mriekki/project-forge` distribution and public ChatGPT contract;
- this public **Project Forge Control Plane** owns invitation/authorization and GitHub-first orchestration;
- private foundational sources own reusable workflow behavior, discovery/generation logic, deployment mechanics, and existing-repository adoption behavior;
- generated or adopted Projects own their product scope, architecture, code/tests, documentation, accepted baselines, deployment facts, and Git/PR/CI state.

Each Builder owns their own Project repositories. This public Control Plane contains only safe request/orchestration and developer-authorization metadata; it must not contain private Project definitions, foundational source topology, GitHub App private keys, PATs, or other credentials.

## Developer authorization

`config/developers.json` is the operational authorization registry. `config/allowed-owners.json` remains a generated authorization projection for existing generation/sync/adoption validators; CI requires it to mirror active developers with `generate-project` capability. Remote adoption is available only to an already-authorized Project Builder who owns the exact target repository.

An already-active Builder can use the doctor issue:

```text
[project-forge-doctor] github-owner
```

The doctor verifies registry state, Project Forge Builder GitHub App installation, and the public Project Forge ChatGPT contract. It is onboarding/readiness evidence, not a per-Project discovery requirement.

Revocation uses:

```text
[revoke-project-forge] github-owner
```

Revocation removes future Control Plane authorization only. It never deletes, transfers, disables, or mutates repositories already owned by the Builder. The tooling refuses to revoke the last active admin.

## Public request model

Generation request:

```text
[generate-project] owner/repository
```

Existing-repository adoption request:

```text
[adopt-project] owner/repository <32-lowercase-hex-request-id>
```

The adoption request ID is opaque correlation only. It is used to identify the short-lived target branch `project-forge/adopt-<request-id>` and must not encode source code, product definition, secrets, private baseline detail, or repository analysis.

Remote Core-sync request:

```text
[sync-core] owner/repository
```

For all request types, the issue body must be empty. Private product definitions, adoption manifests, baseline details, source code, and secrets stay in the target repository.

The request author must match the target owner and be ACTIVE for Project Forge authoring. The `project-forge-*` repository namespace is reserved and is never a valid generic consumer target.

The approved `PROJECT_BOOTSTRAP.json` stays private in a generation target. The approved `PROJECT_ADOPTION.json` stays private on the short-lived adoption seed branch. `CORE_BASELINE.json` stays private in a Core-sync target. Workflows read those files only after minting a short-lived GitHub App installation token scoped to the exact repository.

## GitHub-first generation

The `[generate-project]` workflow:

1. validates the authorized, owner-authored, empty-body request;
2. resolves the accepted private Bootstrap source through protected Actions configuration;
3. reads and validates the private target `PROJECT_BOOTSTRAP.json`;
4. obtains a source-only token and an exact-target token;
5. resolves/verifies the exact public `@mriekki/project-forge` package selected by the approved manifest;
6. runs the canonical deterministic generation path;
7. validates generated baselines and managed-file integrity; and
8. publishes only the validated generated tree without force-pushing.

Normal approved discovery may use `generation.project-forge.integrity: "registry"`. Humans approve the exact package/version/profile, not npm hash plumbing. The generation boundary resolves registry metadata to the **resolved exact SHA-512 integrity**, verifies it before reusable mutation, and records that exact value in generated provenance.

A missing package/version, integrity mismatch, invalid profile, managed-path conflict, unavailable required access, or failed generation is a stop condition. The workflow never silently substitutes another package, source revision, or destination.

## Existing-repository adoption

Remote adoption is a different operation from greenfield generation. The Builder/ChatGPT discovery path first pins and analyzes the exact target default-branch commit read-only, produces a human-approved Adoption-owned `PROJECT_ADOPTION.json`, and seeds only that manifest on a short-lived branch exactly one commit above the analyzed base.

The `[adopt-project]` workflow then:

1. validates the owner-authored, empty-body request and opaque branch correlation;
2. resolves the exact accepted Adoption source from the public Project Forge contract while keeping the private source location in protected Actions configuration;
3. verifies the manifest's exact target, Adoption revision, and Bootstrap discovery revision;
4. refreshes origin/default-branch evidence and fails if the reviewed base moved;
5. invokes the canonical deterministic Adoption apply path, including collision and AI-source guards;
6. commits and pushes only the bounded adoption diff to the existing short-lived branch without force-pushing;
7. opens a target-repository adoption PR; and
8. observes target PR checks when they exist.

No target PR checks is reported exactly as `CI NOT OBSERVED`; it is never converted into a green-CI claim. The workflow never merges the adoption PR, deploys the application, writes to an upstream/source repository, or resolves upstream conflicts. Merge/finalize remains a human decision in the target repository.

## Remote Core sync

The `[sync-core]` workflow remains the narrower Core-specific compatibility path for generated consumers that still use Core-specific sync. The accepted private source is resolved through protected Actions configuration. The workflow validates current baseline integrity, creates a new non-force branch when needed, opens a consumer PR, and reports success only after target PR checks are green. Merge remains a human decision in the consumer repository.

## GitHub App and setup

The public GitHub App display name is **Project Forge Builder**. GitHub's generated App slug/bot username remains an implementation identity and is resolved dynamically rather than guessed.

- Builder onboarding: `docs/SETUP.md`
- Control Plane administrator setup: `docs/ADMIN_SETUP.md`

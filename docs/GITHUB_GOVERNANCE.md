# Project Forge Control Plane GitHub Governance

This document records the intended GitHub administration policy for the public Project Forge Control Plane trust root. Repository files define and test the workflow side of these controls; repository rulesets remain GitHub Settings configuration and must be verified from live repository evidence.

## `main` protection

Use two active repository rulesets targeting the default branch (`main`) so the operational registry bypass cannot weaken history integrity.

### Integrity ruleset — no bypass actors

This ruleset must:

- block branch deletion;
- block non-fast-forward updates / force pushes;
- have no bypass actors at all.

Because Project Forge Builder does not bypass this ruleset, activation/revocation automation can never force-push, rewrite history, or delete `main`.

### Change-control ruleset — one exact App bypass

This ruleset must:

- require changes to land through a pull request for normal engineering work;
- require the stable `CI / required` check before normal PR merge;
- preserve the explicit human merge/finalize decision for code, workflow, and policy changes;
- use **Project Forge Builder** as the only always-allowed bypass actor;
- not grant a repository-role, administrator, individual-user, or generic GitHub Actions bypass.

The App bypass exists only because activation and revocation must persist the operational developer registry and its exact allowlist projection without turning onboarding into a manual code-review ceremony. It bypasses PR/status change control, while the separate integrity ruleset still blocks destructive history operations.

## Registry persistence boundary

Only these workflows may directly persist Control Plane registry state to `main`:

```text
.github/workflows/claim-invitation.yml
.github/workflows/revoke-developer.yml
```

They may stage only:

```text
config/developers.json
config/allowed-owners.json
```

Both workflows:

- validate the requester's authorization before mutation;
- serialize registry writes through `project-forge-developer-registry`;
- validate the registry/projection after mutation and again after any rebase;
- mint a short-lived **Project Forge Builder** installation token scoped to `project-forge-control-plane` only;
- request only `Contents: read and write` for that token, not workflow-write permission;
- use ordinary fast-forward/rebase mechanics and never force-push or rewrite history.

The App bypass is therefore an operational persistence exception, not an engineering-write authority. Changes to the workflows that mint or use the token remain subject to the normal human PR/CI/merge gate.

The Project Forge Builder installation on the Control Plane owner's account must include the `project-forge-control-plane` repository when selected-repository installation is used. Generated Project repositories remain separately selected as needed.

## Safe rehearsal

`Registry Persistence Rehearsal` is a manual, non-authorizing workflow. It mints the same exact-repository Project Forge Builder token used by registry persistence, creates an ephemeral branch pointing at the current `main` commit, verifies it, and deletes it. It never changes `main`, developer authorization, the allowlist projection, a generated Project, or Production state.

Use the rehearsal after the App installation is confirmed and before relying on the change-control ruleset bypass for real activation/revocation. Do not create a real invitation or revoke a real Builder merely to test branch protection.

## Acceptance evidence for issue #107

Before closing the hardening issue, retain evidence that:

1. the integrity ruleset blocks deletion and force/non-fast-forward updates with no bypass actors;
2. the change-control ruleset requires pull requests and `CI / required` for normal engineering changes;
3. the only change-control bypass actor is Project Forge Builder;
4. a normal direct write to `main` is refused while a reviewed PR merge succeeds;
5. `Registry Persistence Rehearsal` succeeds and leaves no rehearsal branch behind;
6. a non-authorizing onboarding self-test still passes;
7. no real developer authorization was changed merely to prove the control.

# Operational Bootstrap source transition — default-off proposal

The live protected read-only source transport at Control Plane run 45038225711
verified 188 original and monorepo Bootstrap files, identical immutable
subtrees and all public contract/projection bytes. That rehearsal did **not**
activate production generation.

This proposal adds a separate, initially disabled operational selector to
Generate Project. When `PF_BOOTSTRAP_MONOREPO_SOURCE_ENABLED` is not exactly
`true`, all generated Projects continue to use the existing original Bootstrap
source and existing accepted public logical revision. Turning on the selector
requires separately reviewed `BOOTSTRAP_OPERATIONAL_SOURCE_BINDING` protected
policy; reusing the preview secret is forbidden. The exact immutable repository
IDs, checked original and selected nested source, permissions and complete tree
comparison are enforced again. App source-only token revocation and exact
source materialization complete **before** the separate target write token is
issued. Generated Project provenance still uses the accepted original public
logical Bootstrap revision: no private locator or new authority leaks into the
public descriptor. Source copy bytes and executable modes are reverified
immediately before use.

No selector activation, remote generation, independent source/security
acceptance, GitHub target mutation, new logical revision, or Production
deployment is granted by this implementation PR. Before activation: obtain
independent E review of this exact source, separately authorize the protected
operational policy and source switch; qualify rollback and a disposable
authorized GitHub target through actual generated/target CI and clean clone.
Do not change Adoption source authority or FMP Production as a side effect.

Optional Household Authentication/Feedback profiles remain *unavailable* in
the active remote generation route until the separately reviewed optional
profile selection, package/archive matching and end-to-end remote proof are
complete. Local tests and synthetic Git handoff are not substitutes.

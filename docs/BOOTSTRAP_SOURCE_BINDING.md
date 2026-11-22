# Bootstrap operational source binding (proposal)

The public descriptor's exact logical Bootstrap revision is a compatibility
identifier, not a public private-source locator. A future protected binding may
map that logical revision to an exact repository ID, immutable checkout commit,
relative source root and whole Git subtree. The same logical revision must never
identify changed subtree bytes; changed source requires a separately accepted
new public revision/contract projection.

The dormant `tools/bootstrap_source_binding.py` verifier compares that proposed
operator-only binding to authenticated private repository identity and to the
accepted public descriptor. It verifies exact clean checkout, whole subtree and
all source working bytes, catalog protocol/version and portable requirements
projection. It does not execute source code. Tests use synthetic repositories,
not real target Projects or source credentials.

**Activation is not part of this change.** The existing generation and
adoption workflows, App token grants, source mapping and target access remain
unchanged. Before switching generation:

- Independently review the new protected binding and exact installation
  identity; ensure source-only read permissions and separate target-only write
  permissions. No private locators or raw source contents in public metadata.
- Preserve existing logical provenance when identical source is relocated,
  verify the exact source subtree before any source execution or target
  mutation, and fail closed if ref, catalog, projection or mapping differs.
- Rehearse a disposable authorized target and wrong-binding/unauthorized-target
  rejection; keep the previous source route available for rollback.
- Separately qualify the exact accepted optional generation profiles and
  matching package/archive for Household Authentication and Feedback.
  Successful local optional generation is not evidence of remote support.
- Do not switch Adoption source authority by changing Bootstrap transport.
  Existing Projects, credentials, deployed applications and Production are
  outside this change.

The verifier result is nonauthorizing; successful CI alone does not establish
live source permissions, approved generation or Production readiness.

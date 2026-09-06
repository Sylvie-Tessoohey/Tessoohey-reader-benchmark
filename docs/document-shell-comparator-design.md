# Future document-shell comparator coverage

Status: design preparation only. The cycle-1 private rerun remains pinned to benchmark commit
`008bd3fe7f194b2f8a3c65754d36f50ca76f058f`.

## Current coverage

The current comparator compares the public `/document` tree after removing IDs, source zones and
technical provenance. This means document-header and excluded-boilerplate **content** differences
are visible through the structure dimension.

However, the current provenance dimension is observation-focused. It does not independently score
geometry for:

- `Document.document_header.source_zone`;
- `Document.excluded_boilerplate[*].source_zone`.

That is a known coverage gap for a future document-shell campaign.

## Required future checks

### Document header

Because the document header is a singleton, compare:

- content through the existing document structure/source-tree check;
- header source zone through the provenance dimension.

Geometry should use the same page-aware compatibility policy as other source evidence:

- page sets must match;
- precise Reader crops may be contained inside broader independently annotated reference crops;
- unrelated extra Reader crops must fail provenance.

Do not use patient name, laboratory name or dates as geometry identity. The header object is already
structurally identified.

### Excluded boilerplate

Boilerplate items need identity matching before geometry comparison.

Identity must not depend on `source_content`, because content is a field being evaluated.

Safe identity evidence can include:

- `reason`;
- page;
- geometry;
- repeated-page context.

If several boilerplate items of the same reason have indistinguishable geometry/context, keep the
match ambiguous instead of pairing by text to improve the score.

After identity is established, compare separately:

- reason;
- source content;
- provenance/source zone.

### Semantic column headings

Do not write comparator logic that assumes every item present in a private reference's
`excluded_boilerplate` list is necessarily correct reference truth forever.

The private reference lifecycle remains authoritative:

- frozen validated references stay frozen for the current campaign;
- modeling corrections require new candidate versions and explicit review;
- comparator behavior must not be changed merely to accommodate an over-specified reference.

## Severity

Document-shell content/provenance errors should remain visible as separate checks. Do not add an
aggregate shell score.

A future policy review may distinguish critical identity/date failures from less critical layout
metadata, but any noncritical error still prevents a functional PASS under the current Gate policy.

## Synthetic adversarial tests

Before enabling shell provenance in a private campaign, add synthetic tests for:

1. correct header content with wrong page geometry;
2. one precise header crop inside a broader reference header zone;
3. unrelated extra header crop;
4. two boilerplate items with swapped text but similar reason;
5. same boilerplate content on different pages;
6. whole-page boilerplate crop replacing a small footer crop;
7. ambiguous same-reason/same-page boilerplate identity;
8. repeated-header copy matched without using patient/result text as identity.

## Sequencing

Do not change the benchmark commit used by the prepared cycle-1 rerun.

Implement this coverage only for the later shell-focused campaign, with its own pinned benchmark
commit and synthetic CI.

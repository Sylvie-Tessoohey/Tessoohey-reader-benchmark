# Benchmark contract-field coverage audit

Status: coverage audit for Gate 1. The prepared cycle-1 rerun remains pinned to benchmark commit
`008bd3fe7f194b2f8a3c65754d36f50ca76f058f`.

This document identifies public Reader contract fields that the current comparator scores, scores
only partially, or does not yet score. A functional PASS from the current comparator must therefore
not be treated as final Gate 1 validation until the material gaps below are closed or explicitly
declared out of Gate scope.

## Public contract layers

The Reader 1.0 public output includes:

- `Document`;
- recursive `Part`;
- recursive `LaboratorySection`;
- `LaboratoryObservation`;
- current representations;
- reference ranges;
- previous results;
- source text / method / comments;
- source zones and technical provenance;
- unclassified elements;
- extraction metadata.

The independent benchmark intentionally ignores runtime-only extraction metadata for documentary
truth, but documentary fields require explicit coverage decisions.

## Currently strong coverage

### Observation identity and presence

The comparator matches observations using:

- source label;
- page/geometry;
- section context;

without using result values, units, ranges or history as identity.

Missing, extra and ambiguous observation identity are explicit.

### Current result source fields

Scoreable checks currently cover:

- source value;
- comparator;
- source unit;
- result type;
- multi-representation association.

### Current versus history

Historical result objects are compared separately from the current result, preventing historical
values from being silently promoted to current values.

### Reference-range semantics

The comparator separately checks:

- condition;
- operator;
- source value/min/max;
- source unit;
- literal source text.

Literal typography ambiguity does not mask wrong semantic bounds.

### Observation provenance

Observation `source_zone` geometry is compared with page-aware containment/overlap rules.

## Partial coverage

### Document

The current `/document` comparison includes source-tree content after removing source zones and
technical provenance.

This sees many content differences, including header/boilerplate content, but:

- all document content is coupled into one noncritical structure check;
- one ambiguous descendant can make the whole document check ambiguous;
- document-header source-zone geometry is not scored;
- boilerplate source-zone geometry is not scored.

A dedicated document-shell comparator design already records the required follow-up.

### Part / section structure

The structural projection currently covers:

- part type/subtype;
- section/subsection source titles.

A newer comparator head narrows ambiguity propagation to those actual structural fields.

However, structural coverage does not yet mean complete part/section coverage.

## Material fields not currently scored

### Part fields

The current comparator does not independently score:

- `Part.languages`;
- `Part.examination_date`;
- `Part.metadata`;
- `Part.source_zone`;
- `Part.provenance`;
- `Part.text_content`;
- `Part.text_blocks`;
- `Part.comment`.

This is material for the private corpus because contract-1.0 references currently preserve report
status, edition dates, laboratory identity, collection-adjacent metadata and other documentary
facts at part scope.

A Reader output can therefore currently omit some part metadata without that omission necessarily
creating a benchmark error.

### LaboratorySection fields

Outside the section title/hierarchy, the comparator does not independently score:

- section method;
- section comment;
- section source zone;
- section technical provenance.

Observation-level method/comment checks do not substitute for section-level association.

### Nested provenance

The provenance dimension currently scores the observation's top-level source zone, but not the
source zones of:

- reference ranges;
- previous results;
- observation method;
- observation comment;
- section method/comment;
- document header;
- excluded boilerplate;
- part metadata / source metadata.

Therefore a value can be textually correct yet attached to the wrong source region without a
dedicated nested-provenance failure.

### Technical provenance

`TechnicalProvenance` is largely excluded from documentary source-tree comparison.

That may be appropriate for some Gate decisions, but it needs an explicit policy rather than
accidental omission.

### SourceText raw audit projections

`Part.text_content` and `Part.text_blocks` are not currently part of the structural projection.

For scanned layouts these fields can carry genuine reading-order ambiguity, so they should not be
naively made PASS-blocking as one giant literal string. Coverage should be designed around:

- source-block completeness;
- region coverage;
- explicit ambiguity;
- source-faithful text where uniquely recoverable.

## Derived normalization fields

Current-result checks emphasize printed source fields. Some derived fields such as numeric
normalization are not uniformly compared across all object types.

Before final Gate 1, explicitly decide which derived normalization fields are:

- required deterministic Reader behavior;
- optional downstream conveniences;
- outside documentary Gate scope.

Do not let a missing policy turn into accidental false PASS or false FAIL.

## False-PASS risk

The highest-priority false-PASS risks before final Gate 1 are:

1. missing/wrong part examination date or metadata;
2. method/comment attached at the wrong section level;
3. correct nested text with wrong nested source zone;
4. missing document-header/boilerplate provenance;
5. incomplete raw source-block coverage hidden behind correct observations.

## Recommended closure order

After the frozen cycle-1 rerun:

1. preserve the rerun evidence unchanged;
2. implement document-shell Reader support and shell comparator provenance;
3. add part examination-date / metadata comparison;
4. add section method/comment association checks;
5. add nested provenance checks;
6. define source-block/text-content completeness policy;
7. define required derived-normalization policy;
8. add adversarial synthetic tests for every newly covered field;
9. pin a new benchmark commit;
10. run the final private Gate corpus with that expanded comparator.

## Gate rule

Until these material coverage gaps are closed, a comparator `PASS` means:

> no detected deviation within the fields currently scored

and not:

> complete proof that every documentary contract field is correct.

That distinction must remain explicit in Gate 1 reporting.

# Gate-level handling of irreducible reference ambiguity

Status: policy clarification for review. This does not change comparator verdicts.

## Why this matters

A source-faithful benchmark can contain genuine documentary ambiguity, especially in scanned
documents where exact punctuation, dash glyphs, whitespace or reading-order linearization cannot be
recovered uniquely.

The benchmark intentionally records those fields as `ambiguity` rather than inventing truth.

Under the current comparator policy, any ambiguity prevents a functional `PASS` and produces
`INCOMPLETE` when the Reader itself succeeded.

That is correct for the comparator. It does **not** imply that every ambiguity requires a Reader
code change.

## Distinguish three states

### PASS

- Reader extraction status is `success`;
- no critical errors;
- no noncritical errors;
- no unannotated fields;
- no reference ambiguities affecting checks.

This is the strongest benchmark outcome.

### Reference-ambiguity-only INCOMPLETE

A case can be diagnostically "reference ambiguity only" when:

- Reader extraction status is `success`;
- critical error count is zero;
- noncritical error count is zero;
- unannotated count is zero;
- one or more remaining checks are `ambiguity`;
- every such ambiguity is explicitly declared by the independently validated reference;
- the Reader output does not contradict any unambiguous source field.

The comparator should still report `INCOMPLETE`, not `PASS`.

At Gate-review level, however, this state should be classified as an irreducible source limitation
rather than a Reader defect.

### Reader PARTIAL / ERROR

A Reader extraction status of `partial` or `error` is not equivalent to reference ambiguity.

A fail-closed Reader collapse, missing semantic assembly or unprocessed region remains a Reader
execution problem even if the source also contains ambiguous typography.

## Gate 1 decision principle

Gate 1 should not require the benchmark to invent a unique string where the source itself does not
support one.

Therefore a final Gate review may accept a case with reference-ambiguity-only `INCOMPLETE` as
documentarily satisfactory **only after** checking that:

1. all scoreable fields match;
2. no Reader error remains;
3. ambiguity was authored independently from Reader output;
4. the ambiguity note explains the source limitation;
5. the Reader did not silently normalize or guess the ambiguous field.

This is a manual Gate-level acceptance rule, not an aggregate score and not a rewrite of comparator
truth.

## Comparator diagnostics

Future campaign summaries may expose a derived diagnostic flag such as
`reference_ambiguity_only: true`, but it must not rename the functional verdict to `PASS`.

The derived flag should be purely mechanical:

- extraction status `success`;
- no critical/noncritical/unannotated checks;
- at least one ambiguity check.

## Current scan relevance

The private scan corpus deliberately contains exact-text ambiguities in low-value scanned
typography and reading-order representations while separately verifying structured result fields.

After Reader defects are corrected, any remaining ambiguity-only outcome should therefore be
reviewed under this policy instead of prompting fabricated punctuation or brittle OCR heuristics.

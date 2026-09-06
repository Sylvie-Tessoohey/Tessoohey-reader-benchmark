# Tessoohey Reader Benchmark

Independent evaluation of **PDF → Module 1 documentary JSON**. Gate 1 is not validated.
This repository contains no production integration, catalogue mapping or real medical data.

## First delivery

- Reference envelope with source SHA-256, byte count, page geometry, annotation coverage,
  candidate/validated status and approval fingerprint.
- Twelve separate comparison dimensions, without a global score.
- Observation matching uses labels, page/geometry and section context; never result values,
  units, reference values or historical results.
- Critical comparisons preserve value/unit pairs, observation/range attachment and
  current/historical separation.
- JSON and Markdown deviation reports; candidate references and partial Reader outputs
  cannot produce a functional PASS.
- Exact Reader and benchmark commits plus the real prompt fingerprint are required for a
  private campaign.
- Adversarial synthetic tests, including swapped values and misleading marginal multisets.

The private corpus and validated references are **not published in this public repository**.
A first real three-case private baseline was executed on 2026-09-06 and remains functionally
non-passing. Public CI still validates synthetic comparator behavior only; real campaign evidence
remains private.

## Use without installation

Python 3.11+; no runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m reader_benchmark.cli validate-reference /private/reference.json
PYTHONPATH=src python -m reader_benchmark.cli compare \
  /private/reference.json /private/reader-output.json /private/run.json \
  --output /private/report.json
PYTHONPATH=src python -m reader_benchmark.cli compare-campaigns \
  /private/baseline-results.zip /private/candidate-results.zip \
  --output /private/campaign-delta.json
```

A single-case comparison writes both `report.json` and `report.md` to the chosen private
directory. `compare-campaigns` accepts complete private result directories or ZIP archives and
writes both JSON and Markdown before/after evidence. It reports per-case count deltas,
per-dimension deltas and check-classification transitions without an aggregate quality score.

Exit codes for a single-case comparison: `0` = functional PASS; `2` = valid comparison with
another verdict; `3` = invalid or inconsistent inputs. Campaign-delta comparison returns `0`
when both evidence bundles are structurally readable; its deltas never by themselves validate
Gate 1. The original Reader statuses are always retained.

## Reference envelope

The JSON document contains:

- `reference_schema_version`: `1.1`;
- `case_id`, `reference_version`;
- `status`: `candidate` or `validated` (reference approval lifecycle);
- `annotation_status`: `incomplete` or `complete` (documentary annotation coverage);
- `source`: `sha256`, `size_bytes`, `page_count`, and `pages` with PDF width/height;
- `documentary_json`: Module 1 schema 1.0 documentary projection, independently authored
  from the PDF: `schema_version`, `document`, `parts`, `unclassified_elements`;
  Reader runtime fields (`status`, `extraction_id`, `errors`, `extraction_metadata`)
  are deliberately absent from this reference projection;
- `observation_inventory`: `complete` or `incomplete`;
- `annotations`: JSON pointers into `documentary_json`, each with `status` and optional `note`;
- `validation`: absent/null for a candidate; for validated references: reviewer,
  validated_at and reference_payload_sha256.

Annotation states are `verified`, `unannotated` and `ambiguous`. A verified author annotation
is not approval of the whole reference. The nearest ancestor applies, while narrower
uncertainty blocks scoring of affected composite fields. No annotation means unannotated.
Null or empty expected values assert absence only inside a verified scope.

Approval fingerprints cover the documentary JSON, annotations, annotation status, source identity, inventory,
case and reference version. Do not regenerate an approval automatically after an edit.
Only an explicit reviewer validation may approve a new reference version. The CLI deliberately
does not contain an automatic "promote to Gold" command.

## Status vocabulary (envelope/report 1.1)

Human-readable reports display three distinct lines: reference validation, annotation
completeness, and Reader extraction. JSON reports expose `reference_status`,
`annotation_status`, and `extraction_status`. The last preserves the upstream Reader
`status` exactly: `success`, `partial`, or `error`. No Reader changes are required.

`complete` annotation requires a complete observation inventory and no unannotated
terminal fields (including empty arrays and nulls). Explicit ambiguities may remain
recorded, but prevent PASS on affected comparisons. Complete annotation does not
mean approved reference or successful extraction. Real printed report wording such
as “Compte rendu partiel” remains literal documentary metadata.

Migration from envelope 1.0: remove execution fields from `documentary_json`, repair
annotation pointers, declare actual annotation completeness, and keep edited references
as candidates until the new payload is explicitly approved. Existing approval fingerprints
cannot be reused. Old reports stay unchanged; new reports use schema 1.1.

## Run manifest

Required fields:

```text
reader_commit: exact 40-character Reader commit SHA
benchmark_commit: exact 40-character benchmark/comparator commit SHA
schema_version: 1.0
provider / model: actual configured provider and model
parameters: actual inference parameters
prompt_version: declared prompt label
prompt_sha256: hash of the actual prompt payload/template used
source: sha256, size_bytes, page_count (must match the reference PDF)
run_date: actual execution timestamp
duration_ms: measured duration
tokens: input_tokens, output_tokens, total_tokens; or null + tokens_unavailable_reason
cost: optional externally calculated amount/currency/pricing date and source
```

Do not label an old run with a newer branch head. If an old report lacks actual prompt
identity, recover it from the executed commit before comparing; never guess. The manifest
is preserved in the report and checked against available Reader output metadata.

## Private campaign harness

`scripts/run_private_campaign.py` runs outside Reader, in a private environment.
It requires exact clean Git checkouts for both the benchmark and Reader, fingerprints the
Reader instruction/request/schema files, requires complete explicitly approved references,
and verifies each PDF before calling AI. Both commits are retained in the private environment,
run manifests and campaign summary. It preserves full private requests/responses, per-call
hashes, output and execution report, package versions, measured usage, and per-case comparison.
Existing outputs cannot be overwritten. SDK retries are disabled and recorded to keep attempt
accounting explicit.

The three-case plan and medical inputs stay private. The harness identity guards have synthetic
tests and the harness has now been exercised in a real private baseline. Never execute it with
real medical inputs in this public repository’s GitHub Actions, and never upload those private
inputs or outputs as public Actions artifacts.

```bash
# Run from the exact benchmark commit named by benchmark_commit in the private plan.
PYTHONPATH=src python scripts/run_private_campaign.py /private/campaign-plan.json \
  --reader-checkout /private/pinned-reader --output /private/new-campaign
```

## Comparison policy

The dimensions are presence, source label, source value, comparator, unit, current vs history,
reference range, association, provenance, structure, extra elements and unclassified content.
Classifications: match, critical_error, noncritical_error, ambiguity, unannotated.

Exact source string comparison is intentional. Label whitespace/case normalization is only
used to find candidate identities. Representation order is ignored while value/unit/comparator
pairs are preserved. Range/history objects keep their associated fields together.
Range bounds, operators, conditions and units are checked together as critical fields;
literal range typography is a separate noncritical check. An uncertain dash must not
mask an incorrect bound. Optional explicit nulls and omitted optional fields are equivalent.

Matching requires mutual unique best candidates. Duplicate/tied identities remain ambiguous.
Incorrectly assigned values stay attached to their source label and are reported as critical.
Without enough identity evidence the report shows missing/extra/ambiguous observations;
it never invents a match to improve the result.

Geometry policy v1 checks in-page finite rectangles and requires the same page set.
Each Reader evidence crop must either reach IoU 0.25 with a reference crop or lie at least
80% inside one. Every independently annotated reference crop must still be touched. This
allows several precise Reader crops to support one broader human reference zone without
accepting whole-page evidence as a substitute for a small observation zone. Geometry remains
a heuristic, not a proof of visual truth; policy changes must be recorded as benchmark versions.

`CANDIDATE_REFERENCE` is reported even when candidate comparisons have errors. Error counts
remain visible. For approved references, Reader `partial`/`error` is retained before any PASS.
Unannotated fields, incomplete inventories and unresolved matching prevent full PASS.

## Boundaries and remaining work

- No deep Reader modifications and no AI calls in this delivery.
- No full Module 1 JSON Schema validator is bundled yet. Input validation targets comparison
  identity, annotation integrity and provenance; authoring checks should also validate against
  the pinned Reader schema. A benchmark PASS is scoped to these checks, never Gate 1 approval.
- Text transcription/boilerplate quality, document-header/boilerplate provenance geometry,
  field-level geometry of nested references and benchmark campaigns across multiple models remain
  to be expanded. A design for future document-shell provenance checks is recorded under
  `docs/document-shell-comparator-design.md`.
- References remain candidates until explicit approval; annotation completeness is tracked separately.
- Real outputs, references and reports must remain in private storage outside Git. Do not
  upload them to this repository's public Actions artifacts.
- The first decision checkpoint follows five reference documents and two generic correction
  cycles, using fixed cases and before/after per-dimension metrics.

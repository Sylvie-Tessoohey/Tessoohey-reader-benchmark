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
- Full commit and real prompt fingerprint required in every run manifest.
- Adversarial synthetic tests, including swapped values and misleading marginal multisets.

The first private corpus selection and first candidate reference are separate deliverables.
They are **not published in this public repository**. No real campaign has been run by this
initial implementation. CI success only validates the synthetic comparator tests.

## Use without installation

Python 3.11+; no runtime dependencies.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m reader_benchmark.cli validate-reference /private/reference.json
PYTHONPATH=src python -m reader_benchmark.cli compare \
  /private/reference.json /private/reader-output.json /private/run.json \
  --output /private/report.json
```

The comparison writes both `report.json` and `report.md` to the chosen private directory.
Exit codes: `0` = functional PASS; `2` = valid comparison with another verdict;
`3` = invalid or inconsistent inputs. The original Reader status is always retained.

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
reader_commit: exact 40-character commit SHA
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

## Comparison policy

The dimensions are presence, source label, source value, comparator, unit, current vs history,
reference range, association, provenance, structure, extra elements and unclassified content.
Classifications: match, critical_error, noncritical_error, ambiguity, unannotated.

Exact source string comparison is intentional. Label whitespace/case normalization is only
used to find candidate identities. Representation order is ignored while value/unit/comparator
pairs are preserved. Range/history objects keep their associated fields together.

Matching requires mutual unique best candidates. Duplicate/tied identities remain ambiguous.
Incorrectly assigned values stay attached to their source label and are reported as critical.
Without enough identity evidence the report shows missing/extra/ambiguous observations;
it never invents a match to improve the result.

Geometry policy v1 checks in-page finite rectangles and requires matching ordered page lists
with IoU at least 0.25. This is a documented initial heuristic, not a proof of visual truth.
Whole-page boxes cannot replace small observation evidence boxes. Calibrate geometry on
verified examples before changing this threshold; record policy changes as benchmark versions.

`CANDIDATE_REFERENCE` is reported even when candidate comparisons have errors. Error counts
remain visible. For approved references, Reader `partial`/`error` is retained before any PASS.
Unannotated fields, incomplete inventories and unresolved matching prevent full PASS.

## Boundaries and remaining work

- No deep Reader modifications and no AI calls in this delivery.
- No full Module 1 JSON Schema validator is bundled yet. Input validation targets comparison
  identity, annotation integrity and provenance; authoring checks should also validate against
  the pinned Reader schema. A benchmark PASS is scoped to these checks, never Gate 1 approval.
- Text transcription/boilerplate quality, field-level geometry of nested references and
  benchmark campaigns across multiple models remain to be expanded.
- References remain candidates until explicit approval; annotation completeness is tracked separately.
- Real outputs, references and reports must remain in private storage outside Git. Do not
  upload them to this repository's public Actions artifacts.
- The first decision checkpoint follows five reference documents and two generic correction
  cycles, using fixed cases and before/after per-dimension metrics.

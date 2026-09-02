# Benchmark development rules

- This project evaluates Reader; do not add catalogue mapping or production writes.
- Keep all technical content in English. Verbatim source evidence keeps its language.
- This repository is public. Commit only code, documentation and explicitly synthetic tests.
- Never commit real PDFs, medical reference JSON, patient identifiers or real run outputs.
- Build references from the original PDF independently of Reader output.
- References remain candidates until an explicitly recorded reviewer validates them.
- Do not change reference truth to improve Reader scores. Use versioned, reviewed corrections.
- Missing annotations, ambiguous matching and partial Reader status must prevent a full PASS.
- Match observations without looking at result values, units, ranges or dates.
- Preserve current/historical and result/reference associations when comparing fields.
- A CI success is not a functional benchmark PASS.
- Test critical false-PASS and false-match cases before changing comparison rules.
- Never run real-data benchmarks in public GitHub Actions. CI uses synthetic fixtures only.

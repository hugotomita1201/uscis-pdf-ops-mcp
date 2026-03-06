# Release Readiness

## Current Status

The package is locally release-ready for `v0.1.0`, pending external publisher setup.

## Local Validation Completed

- `pytest` passed on the current source tree.
- `python -m build` succeeded after excluding repo-local virtualenvs and temp artifacts from the sdist.
- `scripts/package_smoke.sh` passed against the rebuilt wheel.
- `twine check dist/*` passed for both the wheel and sdist.
- Manual end-to-end validation passed on a real blank USCIS Form I-90 (edition dated 01/20/25):
  - `check_fillable_fields` reported `fillable=true`
  - `extract_form_field_info` returned field metadata successfully
  - `check_text_overflow` reported `overflow_count=0`
  - `fill_form(strategy="auto")` selected `pymupdf`
  - `verify_filled_pdf` reported `issues_found=0`

## Key Fixes Added During Validation

- PyMuPDF checkbox writes now prefer the extracted checked export value instead of the encoded widget on-state name. This fixed real USCIS checkbox persistence on the I-90 mailing-address unit field.
- Auto strategy selection now routes mixed-widget fills (checkbox, radio, choice) to `pymupdf` instead of trying `pypdf` first.
- Hatch build excludes repo-local virtualenvs and temp artifacts so packaging is not affected by local validation runs.

## Remaining External Step

- Configure PyPI trusted publishing (pending publisher or equivalent PyPI-side setup) for `hugotomita1201/uscis-pdf-ops-mcp`.
- After that is in place:
  1. push the current commit to `main`
  2. create tag `v0.1.0`
  3. push the tag
  4. let GitHub Actions publish to PyPI and the official MCP registry

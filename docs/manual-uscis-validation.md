# Manual USCIS Validation

Use this checklist before the first public registry-visible release.

## Preconditions

- You have a user-supplied fillable USCIS PDF on disk.
- The PDF contains representative text, checkbox, and selection fields.
- The server is installed from the built package, not just editable source.

## Steps

1. Run `check_fillable_fields` on the PDF and confirm `fillable=true`.
2. Run `extract_form_field_info` and save the JSON output.
3. Build a representative `field_values.json`.
4. Run `check_text_overflow` and shorten any flagged text.
5. Run `fill_form`.
6. Run `verify_filled_pdf`.
7. Require `issues_found=0`.

## Release Rule

If any issue remains after verification, do not publish to PyPI or the official MCP registry.


<!-- mcp-name: io.github.hugotomita1201/uscis-pdf-ops-mcp -->

# USCIS PDF Ops MCP

`uscis-pdf-ops-mcp` is a deterministic MCP server for fillable PDF form operations. It is positioned for USCIS workflows, but it works on any fillable AcroForm PDF supplied by the user.

This server does five things:

- checks whether a PDF is fillable
- extracts real field ids and widget metadata
- estimates text overflow before filling
- fills the form using deterministic PDF strategies
- verifies the filled PDF against intended values

What it does **not** do in `v0.1.0`:

- OCR or scanned-PDF overlay entry
- screenshot rendering
- SharePoint or case-management integration
- legal reasoning or immigration advice

## Installation

### Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev]
```

### Run the server

```bash
uscis-pdf-ops-mcp
```

### Run via `uvx`

```bash
uvx uscis-pdf-ops-mcp
```

## MCP Tool Surface

- `check_fillable_fields(pdf_path)`
- `extract_form_field_info(pdf_path, output_path?)`
- `check_text_overflow(pdf_path, field_values, field_info?, font_size?, font_name?)`
- `fill_form(pdf_path, field_values, output_path?, strategy="auto", autofit=true, field_info?)`
- `verify_filled_pdf(filled_pdf_path, field_values, field_info?, strict=false)`

`field_values` can be passed in three shapes:

```json
[
  {"field_id": "full_name", "page": 1, "value": "Homer Simpson"}
]
```

```json
{
  "field_values": [
    {"field_id": "full_name", "page": 1, "value": "Homer Simpson"}
  ]
}
```

```json
{
  "full_name": "Homer Simpson"
}
```

## End-to-End Example

```python
from uscis_pdf_ops.core.field_info import extract_form_field_info
from uscis_pdf_ops.core.fill import fill_form

pdf_path = "/absolute/path/to/blank-form.pdf"
field_info = extract_form_field_info(pdf_path)

field_values = {
    "full_name": "Homer Simpson",
    "mailing_address": "742 Evergreen Terrace"
}

result = fill_form(pdf_path, field_values, field_info=field_info)
print(result)
```

## Validation Gate

Before publishing:

- `pytest` passes
- `python -m build` succeeds
- packaged CLI starts cleanly
- MCP Inspector smoke test passes
- one real user-supplied USCIS fillable form completes extract -> fill -> verify with `0` issues

See [manual USCIS validation](/Users/hugo/uscis-pdf-ops-mcp/docs/manual-uscis-validation.md) and [release scripts](/Users/hugo/uscis-pdf-ops-mcp/scripts/inspector_smoke.sh).


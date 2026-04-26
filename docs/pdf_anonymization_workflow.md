# PDF Anonymization Workflow (Local Only)

This workflow anonymizes sensitive brokerage PDF reports **locally** before they are shared, uploaded, or used in automation.

## Safety principles

- Never commit source sensitive PDFs.
- Never upload unredacted PDFs to GitHub/Codex.
- Keep redaction terms in `config/redaction_terms.txt` (gitignored).
- Always manually visually review the anonymized output before sharing.

## Script

- `scripts/anonymize_pdf.py`

It uses **PyMuPDF redaction annotations** and `apply_redactions()` to remove content from PDF pages (not just overlay black boxes).

## Setup

```bash
pip install pymupdf
```

Create your private terms file from the template:

```bash
cp config/redaction_terms.example.txt config/redaction_terms.txt
# then edit with your own account numbers, names, addresses, emails, etc.
```

## Expected local command

```bash
python scripts/anonymize_pdf.py \
  --input data/private/raw/TransactionBalance_original.pdf \
  --output data/raw_trades/samples/anonymized/saxo_full_report_anonymized.pdf \
  --terms-file config/redaction_terms.txt
```

## What gets redacted

1. Exact sensitive terms from `config/redaction_terms.txt`.
2. Built-in sensitive patterns:
   - email addresses
   - phone numbers
   - account/customer-id style text patterns
   - long numeric IDs (8+ digits)
3. Repeated header and footer regions by page ratios.
4. PDF document metadata fields (title/author/subject/keywords/etc).

## Validation behavior

After saving the anonymized PDF, the script re-extracts text and validates that configured terms/patterns are gone.

- If a configured term is **not found** in the source, the script logs a warning and continues.
- If sensitive patterns/terms still appear in output text, validation fails with an error.

## Outputs

- Anonymized PDF at the `--output` path.
- Audit JSON log (default: `<output>.audit.json`) including:
  - pages processed
  - redaction hits by term/pattern
  - pages with redactions
  - output path
  - warnings

## Limitations

- Validation is text-based; it may not catch image-only embedded sensitive data.
- Header/footer blanket redaction may remove non-sensitive content.
- OCR quality in scanned PDFs affects detection.
- Manual visual review is still required before any upload.

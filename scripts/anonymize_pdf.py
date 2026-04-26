#!/usr/bin/env python3
"""Local utility to anonymize sensitive brokerage PDF reports.

Uses PyMuPDF redaction annotations + apply_redactions for true content removal.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - runtime dependency guard
    fitz = None


PATTERN_DEFS: dict[str, str] = {
    "email": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}\b",
    "account_number": r"\b(?:account|acct|a/c|cust(?:omer)?\s*id)\s*[:#-]?\s*[A-Z0-9-]{5,}\b",
    "long_numeric_id": r"\b\d{8,}\b",
}


@dataclass(frozen=True)
class RedactionFinding:
    label: str
    page_number: int
    text: str


def load_terms(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Terms file not found: {path}")

    terms: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


def compile_term_patterns(terms: Iterable[str]) -> dict[str, re.Pattern[str]]:
    patterns: dict[str, re.Pattern[str]] = {}
    for term in terms:
        patterns[f"term:{term}"] = re.compile(re.escape(term), re.IGNORECASE)
    return patterns


def compile_builtin_patterns() -> dict[str, re.Pattern[str]]:
    return {label: re.compile(pattern, re.IGNORECASE) for label, pattern in PATTERN_DEFS.items()}


def _add_redaction(page, rect) -> None:
    page.add_redact_annot(rect, fill=(0, 0, 0))


def redact_header_footer(page, header_ratio: float, footer_ratio: float) -> int:
    page_rect = page.rect
    redactions = 0

    if header_ratio > 0:
        header_rect = fitz.Rect(
            page_rect.x0,
            page_rect.y0,
            page_rect.x1,
            page_rect.y0 + (page_rect.height * header_ratio),
        )
        _add_redaction(page, header_rect)
        redactions += 1

    if footer_ratio > 0:
        footer_rect = fitz.Rect(
            page_rect.x0,
            page_rect.y1 - (page_rect.height * footer_ratio),
            page_rect.x1,
            page_rect.y1,
        )
        _add_redaction(page, footer_rect)
        redactions += 1

    return redactions


def find_text_instances(page, patterns: dict[str, re.Pattern[str]]) -> list[RedactionFinding]:
    findings: list[RedactionFinding] = []
    text = page.get_text("text")

    for label, pattern in patterns.items():
        for match in pattern.finditer(text):
            findings.append(
                RedactionFinding(
                    label=label,
                    page_number=page.number + 1,
                    text=match.group(0),
                )
            )

    return findings


def apply_findings_redactions(page, findings: Iterable[RedactionFinding]) -> int:
    total = 0
    for finding in findings:
        for rect in page.search_for(finding.text):
            _add_redaction(page, rect)
            total += 1
    return total


def build_validation_patterns(terms: list[str]) -> dict[str, re.Pattern[str]]:
    patterns = compile_builtin_patterns()
    patterns.update(compile_term_patterns(terms))
    return patterns


def validate_output(output_pdf: Path, terms: list[str]) -> tuple[bool, list[str]]:
    patterns = build_validation_patterns(terms)
    if fitz is None:
        raise RuntimeError('PyMuPDF is required. Install with: pip install pymupdf')
    doc = fitz.open(output_pdf)
    remaining: list[str] = []
    try:
        full_text = "\n".join(page.get_text("text") for page in doc)
        for label, pattern in patterns.items():
            if pattern.search(full_text):
                remaining.append(label)
    finally:
        doc.close()

    return not remaining, sorted(set(remaining))


def anonymize_pdf(
    input_pdf: Path,
    output_pdf: Path,
    terms_file: Path,
    audit_log_path: Path | None = None,
    header_ratio: float = 0.08,
    footer_ratio: float = 0.08,
) -> dict:
    if fitz is None:
        raise RuntimeError('PyMuPDF is required. Install with: pip install pymupdf')

    terms = load_terms(terms_file)
    all_patterns = build_validation_patterns(terms)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if audit_log_path is None:
        audit_log_path = output_pdf.with_suffix(output_pdf.suffix + ".audit.json")

    doc = fitz.open(input_pdf)
    page_count = doc.page_count
    pages_with_redactions: set[int] = set()
    hit_counter: Counter[str] = Counter()
    warnings: list[str] = []
    total_annots = 0

    try:
        for page in doc:
            page_num = page.number + 1
            page_annots = redact_header_footer(page, header_ratio=header_ratio, footer_ratio=footer_ratio)

            findings = find_text_instances(page, all_patterns)
            if findings:
                pages_with_redactions.add(page_num)
            for finding in findings:
                hit_counter[finding.label] += 1

            page_annots += apply_findings_redactions(page, findings)
            if page_annots:
                pages_with_redactions.add(page_num)
            total_annots += page_annots

            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        metadata = defaultdict(str)
        metadata.update({
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
            "creationDate": "",
            "modDate": "",
        })
        doc.set_metadata(dict(metadata))
        doc.save(output_pdf, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    for term in terms:
        label = f"term:{term}"
        if hit_counter[label] == 0:
            warnings.append(f"term not found: {term}")

    valid, remaining = validate_output(output_pdf, terms)
    if not valid:
        raise RuntimeError(
            "Validation failed: sensitive terms/patterns still present in output -> "
            + ", ".join(remaining)
        )

    audit = {
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "terms_file": str(terms_file),
        "pages_processed": page_count,
        "total_redaction_annotations": total_annots,
        "redaction_hits_by_label": dict(hit_counter),
        "pages_with_redactions": sorted(pages_with_redactions),
        "warnings": warnings,
        "validation": "passed",
        "manual_review_required": True,
        "manual_review_note": "Visual manual review is still required before upload/sharing.",
    }

    audit_log_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Anonymize sensitive data in a brokerage PDF report.")
    parser.add_argument("--input", required=True, type=Path, help="Input source PDF path (local/private).")
    parser.add_argument("--output", required=True, type=Path, help="Output anonymized PDF path.")
    parser.add_argument("--terms-file", required=True, type=Path, help="Redaction terms file path.")
    parser.add_argument("--audit-log", type=Path, default=None, help="Optional audit log output path (JSON).")
    parser.add_argument("--header-ratio", type=float, default=0.08, help="Top-of-page redaction ratio (0..1).")
    parser.add_argument("--footer-ratio", type=float, default=0.08, help="Bottom-of-page redaction ratio (0..1).")
    return parser.parse_args()


def main() -> int:
    if fitz is None:
        raise SystemExit('PyMuPDF is required. Install with: pip install pymupdf')

    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input PDF does not exist: {args.input}")

    if args.header_ratio < 0 or args.footer_ratio < 0:
        raise SystemExit("header/footer ratios must be >= 0")

    audit = anonymize_pdf(
        input_pdf=args.input,
        output_pdf=args.output,
        terms_file=args.terms_file,
        audit_log_path=args.audit_log,
        header_ratio=args.header_ratio,
        footer_ratio=args.footer_ratio,
    )

    print("Anonymization complete.")
    print(f"Output PDF: {audit['output_pdf']}")
    print(f"Audit log: {args.audit_log or str(Path(audit['output_pdf']).with_suffix(Path(audit['output_pdf']).suffix + '.audit.json'))}")
    print("Manual visual review is still required before uploading the anonymized PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

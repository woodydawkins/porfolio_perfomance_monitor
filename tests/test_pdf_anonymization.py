from pathlib import Path

import pytest

from scripts import anonymize_pdf


class FakePage:
    def __init__(self, text: str):
        self._text = text
        self.number = 0
        self.redactions = []

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self._text

    def search_for(self, term: str):
        if term in self._text:
            return [(0, 0, 10, 10)]
        return []

    def add_redact_annot(self, rect, fill):
        self.redactions.append((rect, fill))


def test_load_terms_ignores_comments_and_blanks(tmp_path: Path):
    terms_file = tmp_path / "redaction_terms.txt"
    terms_file.write_text("# comment\n\nJohn Doe\n  12644841 \n", encoding="utf-8")

    terms = anonymize_pdf.load_terms(terms_file)

    assert terms == ["John Doe", "12644841"]


def test_find_text_instances_detects_term_and_email_pattern():
    page = FakePage("Contact john@example.com for account 12644841")
    patterns = anonymize_pdf.build_validation_patterns(["12644841"])

    findings = anonymize_pdf.find_text_instances(page, patterns)
    labels = {f.label for f in findings}

    assert "email" in labels
    assert "term:12644841" in labels


def test_apply_findings_redactions_adds_annotations():
    page = FakePage("Intel Corp.")
    findings = [
        anonymize_pdf.RedactionFinding(label="term:Intel Corp.", page_number=1, text="Intel Corp."),
    ]

    count = anonymize_pdf.apply_findings_redactions(page, findings)

    assert count == 1
    assert len(page.redactions) == 1


def test_load_terms_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        anonymize_pdf.load_terms(tmp_path / "missing.txt")

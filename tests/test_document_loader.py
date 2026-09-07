from tenderrisk.document_loader import (
    MAX_EXTRACTED_CLAUSES,
    _looks_like_heading,
    extract_clauses_from_document,
)


def test_sentence_lines_are_not_treated_as_headings() -> None:
    assert not _looks_like_heading(
        "The contractor shall submit payment records and supporting documents within seven days."
    )


def test_title_case_clause_lines_remain_headings() -> None:
    assert _looks_like_heading("Payment Terms")
    assert _looks_like_heading("10.3")


def test_extraction_coalesces_excessive_sections(monkeypatch) -> None:
    sections = [(f"Heading {index}", "Clause text " * 20, index) for index in range(401)]
    monkeypatch.setattr(
        "tenderrisk.document_loader.extract_text_from_any_document",
        lambda _: "Extracted tender text " * 100,
    )
    monkeypatch.setattr("tenderrisk.document_loader._split_pdf_into_sections", lambda _: sections)

    clauses = extract_clauses_from_document("tender.pdf")

    assert len(clauses) <= MAX_EXTRACTED_CLAUSES

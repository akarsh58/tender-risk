from tenderrisk.document_loader import _looks_like_heading


def test_sentence_lines_are_not_treated_as_headings() -> None:
    assert not _looks_like_heading(
        "The contractor shall submit payment records and supporting documents within seven days."
    )


def test_title_case_clause_lines_remain_headings() -> None:
    assert _looks_like_heading("Payment Terms")
    assert _looks_like_heading("10.3")

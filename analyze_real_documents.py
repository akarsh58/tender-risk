"""Analyze real tender documents from PDFs and JSON files."""

import json
import sys

from tenderrisk.document_loader import load_all_documents
from tenderrisk.schemas import TenderRequest
from tenderrisk.service import analyze_tender


try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


print("Loading documents from pdfs folder...\n")

# Load all clauses from PDF and JSON files
clauses = load_all_documents("pdfs")

if not clauses:
    print("No clauses found in pdfs folder!")
    raise SystemExit(1)

print(f"\nTotal clauses loaded: {len(clauses)}\n")

# Create a request with real documents
request = TenderRequest(
    PROJECT_CONTEXT="Risk analysis for tender documents extracted from PDF and JSON files.",
    QUESTION_OR_MODE="FULL_RISK_SCAN",
    RISK_CATEGORIES=["Payment", "Warranty", "Termination", "Scope & Variations"],
    CONTEXT_CLAUSES=clauses,
)

print("Analyzing tender documents...")
print("=" * 60)

# Analyze the tender
result = analyze_tender(request)

# Print the analysis with UTF-8 output
output = result.model_dump_json(indent=2, ensure_ascii=False)
print(output.encode("utf-8", errors="replace").decode("utf-8"))

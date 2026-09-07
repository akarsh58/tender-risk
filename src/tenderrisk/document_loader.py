"""Load tender documents from PDFs, DOCX, DOC and JSON files into clause objects."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tenderrisk.schemas import Clause


class DocumentLoadError(ValueError):
    """Raised when a document cannot be parsed into valid clause data."""


try:
    import docx  # type: ignore
except ImportError:  # pragma: no cover
    docx = None

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    import PyPDF2  # type: ignore
except ImportError:  # pragma: no cover
    PyPDF2 = None


RISK_KEYWORDS = {
    "payment",
    "invoice",
    "retention",
    "set-off",
    "milestone",
    "termination",
    "suspension",
    "default",
    "liquidated damages",
    "delay damages",
    "performance security",
    "guarantee",
    "bond",
    "scope",
    "variation",
    "claims",
    "disputes",
    "arbitration",
    "warranty",
    "defects",
    "liability",
    "indemnity",
}


def _clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_text_with_fitz(pdf_path: str) -> str:
    if fitz is None:
        raise ImportError("PyMuPDF is required. Install with: pip install pymupdf")

    pages: list[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            text = page.get_text("text")
            if not text:
                continue
            pages.append(f"--- Page {page_index + 1} ---\n{text}")
    finally:
        doc.close()
    return "\n".join(pages)


def _extract_text_with_pdfplumber(pdf_path: str) -> str:
    if pdfplumber is None:
        raise ImportError("pdfplumber is required. Install with: pip install pdfplumber")

    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text:
                pages.append(f"--- Page {page_index} ---\n{text}")
    return "\n".join(pages)


def _extract_text_with_pypdf(pdf_path: str) -> str:
    if PyPDF2 is None:
        raise ImportError("PyPDF2 is required. Install with: pip install PyPDF2")

    pages: list[str] = []
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text:
                pages.append(f"--- Page {page_index} ---\n{text}")
    return "\n".join(pages)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF using the best available engine."""
    for extractor in (_extract_text_with_fitz, _extract_text_with_pdfplumber, _extract_text_with_pypdf):
        try:
            return extractor(pdf_path)
        except Exception:
            continue
    raise ImportError("No PDF extraction library is installed. Install pymupdf, pdfplumber, or PyPDF2.")


def extract_text_from_docx(docx_path: str) -> str:
    """Extract text from a DOCX file."""
    if docx is None:
        raise ImportError("python-docx is required. Install with: pip install python-docx")

    document = docx.Document(docx_path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(paragraphs)


def extract_text_from_doc(doc_path: str) -> str:
    """Extract text from a legacy DOC file using system tools when available."""
    antiword = shutil.which("antiword")
    if antiword:
        result = subprocess.run([antiword, str(doc_path)], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        source = Path(doc_path)
        output_dir = source.parent
        convert_cmd = [
            soffice,
            "--headless",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(output_dir),
            str(source),
        ]
        subprocess.run(convert_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        txt_path = source.with_suffix(".txt")
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8", errors="ignore")

    try:
        import pypandoc  # type: ignore
    except ImportError:
        pypandoc = None

    if pypandoc is not None:
        converted = pypandoc.convert_file(str(doc_path), "plain")
        if converted and converted.strip():
            return converted

    raise ImportError("No DOC extraction tool is available. Install antiword, LibreOffice, or pypandoc.")


def extract_text_from_any_document(path: str) -> str:
    """Extract text from a supported document file type."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".doc":
        return extract_text_from_doc(path)
    raise ValueError(f"Unsupported document type: {suffix}")


def _looks_like_heading(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > 120:
        return False
    if re.fullmatch(r"(?:[0-9]+(?:\.[0-9]+)*|[A-Z][A-Za-z0-9&/()\- ]+)", text):
        return True
    if re.fullmatch(r"(?:Section|Clause|Article|Part|Subclause|Item|Schedule)\s*[:\-]?[\w\d\s\&/()\-\.]*", text, re.IGNORECASE):
        return True
    lower = text.lower()
    if lower in RISK_KEYWORDS:
        return True
    if any(keyword in lower for keyword in RISK_KEYWORDS):
        return True
    return False


def _split_pdf_into_sections(pdf_text: str) -> list[tuple[str, str, int]]:
    lines = pdf_text.splitlines()
    sections: list[tuple[str, str, int]] = []
    current_heading: str | None = None
    current_body: list[str] = []
    current_page = 1

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current_heading and current_body:
                current_body.append("")
            continue

        page_match = re.search(r"--- Page (\d+) ---", raw_line)
        if page_match:
            current_page = int(page_match.group(1))
            continue

        if _looks_like_heading(line):
            if current_heading:
                body_text = " ".join(part for part in current_body if part).strip()
                if body_text:
                    sections.append((current_heading, body_text, current_page))
            current_heading = line
            current_body = []
            continue

        if current_heading:
            current_body.append(line)
        elif len(line) > 40:
            current_heading = "Document Section"
            current_body.append(line)

    if current_heading:
        body_text = " ".join(part for part in current_body if part).strip()
        if body_text:
            sections.append((current_heading, body_text, current_page))

    if not sections:
        chunks: list[tuple[str, str, int]] = []
        for page_index, paragraph in enumerate(re.split(r"\n\s*\n+", pdf_text), start=1):
            clean = _clean_text(paragraph)
            if len(clean) < 80:
                continue
            chunks.append((f"Document Section {page_index}", clean, page_index))
        return chunks

    return sections


def extract_clauses_from_document(file_path: str) -> list[Clause]:
    """Extract clause-like sections from a supported document file."""
    text = extract_text_from_any_document(file_path)
    sections = _split_pdf_into_sections(text)

    clauses: list[Clause] = []
    for idx, (heading, body, page_num) in enumerate(sections, start=1):
        clean_body = _clean_text(body)
        if len(clean_body) < 25:
            continue
        if len(clean_body) > 1200:
            clean_body = clean_body[:1200]

        heading_text = heading.strip()
        clause = Clause(
            clause_id=f"DOC-{idx:03d}",
            heading=heading_text or f"Document Section {idx}",
            page=page_num,
            text=clean_body,
        )
        clauses.append(clause)

    return clauses


def extract_clauses_from_pdf(pdf_path: str) -> list[Clause]:
    """Backward-compatible alias for PDF-only extraction."""
    return extract_clauses_from_document(pdf_path)


def load_clauses_from_json(json_path: str) -> list[Clause]:
    """Load a JSON clause array, failing explicitly when it is invalid."""
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DocumentLoadError(f"Could not read valid JSON from {json_path}: {exc}") from exc

    if not isinstance(data, list):
        raise DocumentLoadError("JSON document must contain an array of clause objects.")

    clauses: list[Clause] = []
    for clause_data in data:
        if not isinstance(clause_data, dict):
            raise DocumentLoadError("Every JSON array item must be a clause object.")
        try:
            clauses.append(
                Clause(
                    clause_id=str(clause_data.get("clause_id", "")),
                    heading=str(clause_data.get("heading", "")),
                    page=clause_data.get("page", 1),
                    text=str(clause_data.get("text", "")),
                )
            )
        except ValueError as exc:
            raise DocumentLoadError(f"Invalid clause object: {exc}") from exc

    if not clauses:
        raise DocumentLoadError("JSON document did not contain any clause objects.")
    return clauses


def load_all_documents(folder: str = "pdfs") -> list[Clause]:
    """Load all clauses from PDF and JSON files in the folder."""
    all_clauses: list[Clause] = []
    doc_folder = Path(folder)

    if not doc_folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return all_clauses

    for json_file in sorted(doc_folder.glob("*.json")):
        print(f"Loading JSON: {json_file.name}")
        clauses = load_clauses_from_json(str(json_file))
        all_clauses.extend(clauses)
        print(f"  [OK] Loaded {len(clauses)} clauses")

    for pdf_file in sorted(doc_folder.glob("*.pdf")):
        print(f"Loading PDF: {pdf_file.name}")
        clauses = extract_clauses_from_pdf(str(pdf_file))
        all_clauses.extend(clauses)
        print(f"  [OK] Loaded {len(clauses)} clauses")

    for docx_file in sorted(doc_folder.glob("*.docx")):
        print(f"Loading DOCX: {docx_file.name}")
        clauses = extract_clauses_from_document(str(docx_file))
        all_clauses.extend(clauses)
        print(f"  [OK] Loaded {len(clauses)} clauses")

    for doc_file in sorted(doc_folder.glob("*.doc")):
        print(f"Loading DOC: {doc_file.name}")
        clauses = extract_clauses_from_document(str(doc_file))
        all_clauses.extend(clauses)
        print(f"  [OK] Loaded {len(clauses)} clauses")

    return all_clauses


def list_pdf_files(folder: str = "pdfs") -> list[str]:
    """List all PDF files in the documents folder."""
    pdf_folder = Path(folder)
    if not pdf_folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return []
    return [str(path) for path in sorted(pdf_folder.glob("*.pdf"))]


def list_docx_files(folder: str = "pdfs") -> list[str]:
    """List all DOCX files in the documents folder."""
    doc_folder = Path(folder)
    if not doc_folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return []
    return [str(path) for path in sorted(doc_folder.glob("*.docx"))]


def list_doc_files(folder: str = "pdfs") -> list[str]:
    """List all legacy DOC files in the documents folder."""
    doc_folder = Path(folder)
    if not doc_folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return []
    return [str(path) for path in sorted(doc_folder.glob("*.doc"))]


def list_json_files(folder: str = "pdfs") -> list[str]:
    """List all JSON files in the documents folder."""
    json_folder = Path(folder)
    if not json_folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return []
    return [str(path) for path in sorted(json_folder.glob("*.json"))]


if __name__ == "__main__":
    print("Available PDF files:")
    pdfs = list_pdf_files()
    if pdfs:
        for pdf in pdfs:
            print(f"  - {pdf}")
    else:
        print("  No PDF files found in 'pdfs' folder")

    print("\nAvailable DOCX files:")
    docx_files = list_docx_files()
    if docx_files:
        for docx_file in docx_files:
            print(f"  - {docx_file}")
    else:
        print("  No DOCX files found in 'pdfs' folder")

    print("\nAvailable DOC files:")
    doc_files = list_doc_files()
    if doc_files:
        for doc_file in doc_files:
            print(f"  - {doc_file}")
    else:
        print("  No DOC files found in 'pdfs' folder")

    print("\nAvailable JSON clause files:")
    jsons = list_json_files()
    if jsons:
        for json_file in jsons:
            print(f"  - {json_file}")
    else:
        print("  No JSON files found in 'pdfs' folder")

    print("\nTo use:")
    print("  1. Place PDF, DOCX, DOC, or JSON clause files in the 'pdfs' folder")
    print("  2. load_all_documents() - Loads all supported document types")
    print("  3. For file-specific extraction: extract_text_from_pdf(), extract_text_from_docx(), extract_text_from_doc()")

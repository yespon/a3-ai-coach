import re
import subprocess
from io import BytesIO
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader


def _extract_docx_text(raw_bytes: bytes) -> str:
    try:
        with ZipFile(BytesIO(raw_bytes)) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ElementTree.fromstring(xml_bytes)
    except (BadZipFile, KeyError, ElementTree.ParseError, ValueError):
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []

    for paragraph in root.findall(".//w:p", ns):
        text = "".join(paragraph.itertext()).strip()
        if text:
            paragraphs.append(text)

    if not paragraphs:
        text = "".join(root.itertext()).strip()
        return text

    return "\n".join(paragraphs)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw_bytes))
    except Exception:
        return ""

    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            chunks.append(text)

    return "\n".join(chunks)


def _extract_printable_strings(raw_bytes: bytes) -> str:
    text_parts: list[str] = []

    ascii_runs = re.findall(rb"[\x20-\x7e\t\r\n]{6,}", raw_bytes)
    if ascii_runs:
        text_parts.append("\n".join(run.decode("latin-1", errors="ignore") for run in ascii_runs[:200]))

    utf16 = raw_bytes.decode("utf-16-le", errors="ignore")
    utf16_clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", utf16)
    utf16_lines = [line.strip() for line in utf16_clean.splitlines() if len(line.strip()) >= 6]
    if utf16_lines:
        text_parts.append("\n".join(utf16_lines[:200]))

    return "\n".join(part for part in text_parts if part).strip()


def _extract_doc_text(raw_bytes: bytes) -> str:
    # Prefer antiword when available, then fall back to binary string extraction.
    try:
        with NamedTemporaryFile(suffix=".doc", delete=True) as tmp:
            tmp.write(raw_bytes)
            tmp.flush()
            completed = subprocess.run(
                ["antiword", "-w", "0", tmp.name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                return completed.stdout
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass

    return _extract_printable_strings(raw_bytes)

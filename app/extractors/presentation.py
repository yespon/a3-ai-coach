"""PPTX (PowerPoint) text extractor.

Follows the same ZIP→XML pattern as document.py's DOCX extractor.
PPTX files are ZIP archives containing slide XML at ppt/slides/slideN.xml.
Text lives in <a:t> elements under the DrawingML namespace.
"""

import re
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def _extract_pptx_text(raw_bytes: bytes) -> str:
    """Extract all text from a PPTX file, organized by slide.

    Returns a string with one ``[Slide N]`` header per slide followed by
    the concatenated text content.  Returns ``""`` on any parse failure.
    """
    try:
        zf = ZipFile(BytesIO(raw_bytes))
    except (BadZipFile, Exception):
        return ""

    try:
        # Discover slide files and sort numerically (slide1 < slide2 < slide10).
        slide_entries: list[tuple[int, str]] = []
        for name in zf.namelist():
            m = _SLIDE_RE.match(name)
            if m:
                slide_entries.append((int(m.group(1)), name))

        if not slide_entries:
            return ""

        slide_entries.sort(key=lambda t: t[0])

        chunks: list[str] = []
        for slide_num, entry_name in slide_entries:
            try:
                xml_bytes = zf.read(entry_name)
            except (KeyError, Exception):
                continue

            try:
                root = ElementTree.fromstring(xml_bytes)
            except ElementTree.ParseError:
                continue

            texts: list[str] = []
            for t_elem in root.iter(f"{{{ _DRAWINGML_NS}}}t"):
                text = (t_elem.text or "").strip()
                if text:
                    texts.append(text)

            if texts:
                chunks.append(f"[Slide {slide_num}]")
                chunks.append(" ".join(texts))

        return "\n".join(chunks)
    except Exception:
        return ""
    finally:
        zf.close()

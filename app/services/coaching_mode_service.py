"""Coaching mode detection service.

Determines whether a session should use gangbiao (岗标) or A3 (A3工作法)
coaching mode based on the uploaded file and user message.

Detection priority (highest to lowest):
1. Explicit user keywords in the message
2. File extension (.pptx → always A3)
3. XLSX header detection (gangbiao columns → gangbiao)
4. DOCX content keywords (A3 section markers → A3)
5. Default: gangbiao (backward compatible)
"""

import re

# --- Mode constants ---
MODE_GANGBIAO = "gangbiao"
MODE_A3 = "a3"

# --- A3 section keywords (used as section headers in A3 reports) ---
_A3_SECTION_KEYWORDS = re.compile(
    r"(?:^|\n)\s*(?:\d+[.、）)]\s*)?"
    r"(?:背景|现状|目标|根因|对策|计划|跟进|成果)"
    r"\s*[:：]?\s*(?:\n|$)",
    re.MULTILINE,
)

# --- Gangbiao header keywords from the spreadsheet structured preview ---
_GANGBIAO_HEADER_RE = re.compile(
    r"\[Structured\]\s*识别列:\s*(.*)",
)

_GANGBIAO_CANONICAL_COLUMNS = {"岗位价值", "岗位任务", "任务目的", "任务成果"}

# --- User keyword triggers ---
_A3_USER_KEYWORDS = re.compile(
    r"(?:A3|A3教练|A3工作法|A3课题|A3报告|A3辅导)",
)

_GANGBIAO_USER_KEYWORDS = re.compile(
    r"(?:岗标|岗位标准化|岗位价值|岗位任务|岗位效能|帮我过岗标|岗标辅导)",
)


def detect_coaching_mode(
    filename: str,
    excerpt: str,
    user_message: str = "",
) -> str:
    """Detect the appropriate coaching mode from file and message context.

    Args:
        filename: The uploaded file's name (e.g. "report.pptx").
        excerpt: The extracted text content from the file (may include
            structured preview markers like ``[Structured] 识别列:``).
        user_message: The user's text message (if any).

    Returns:
        ``"gangbiao"`` or ``"a3"``.
    """
    # Priority 1: Explicit user keywords override everything.
    if user_message:
        if _A3_USER_KEYWORDS.search(user_message):
            return MODE_A3
        if _GANGBIAO_USER_KEYWORDS.search(user_message):
            return MODE_GANGBIAO

    lower_name = filename.lower().strip()

    # Priority 2: .pptx → always A3 (gangbiao never uses PPTX).
    if lower_name.endswith(".pptx"):
        return MODE_A3

    # Priority 3: XLSX header detection.
    # The spreadsheet extractor outputs lines like:
    #   [Structured] 识别列: 岗位价值->A列, 岗位任务->C列
    # Count how many of the 4 canonical gangbiao columns were recognized.
    if lower_name.endswith((".xlsx", ".xls")):
        gangbiao_count = _count_gangbiao_headers(excerpt)
        if gangbiao_count >= 3:
            return MODE_GANGBIAO
        # If the excerpt has structured preview data but fewer than 3 gangbiao
        # headers, it's likely an A3 or generic spreadsheet → A3.
        if gangbiao_count > 0 or "[Structured]" in excerpt:
            return MODE_A3
        # No structured preview at all — insufficient signal, fall through to default.

    # Priority 4: DOCX content heuristic.
    if lower_name.endswith((".docx", ".doc")):
        a3_matches = len(_A3_SECTION_KEYWORDS.findall(excerpt))
        # If 3+ A3 section markers found, classify as A3.
        if a3_matches >= 3:
            return MODE_A3
        # Check for gangbiao keywords in the document.
        gb_count = sum(
            1 for kw in _GANGBIAO_CANONICAL_COLUMNS if kw in excerpt
        )
        if gb_count >= 3:
            return MODE_GANGBIAO
        # Ambiguous DOCX: default to A3 (DOCX is more commonly used for A3 reports).
        return MODE_A3

    # Priority 5: Default to gangbiao for backward compatibility.
    return MODE_GANGBIAO


def _count_gangbiao_headers(excerpt: str) -> int:
    """Count how many gangbiao canonical columns appear in the structured preview."""
    match = _GANGBIAO_HEADER_RE.search(excerpt)
    if not match:
        return 0
    header_line = match.group(1)
    count = 0
    for col in _GANGBIAO_CANONICAL_COLUMNS:
        if col in header_line:
            count += 1
    return count
